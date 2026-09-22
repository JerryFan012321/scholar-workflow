"""Persistent per-paper conformance batches with one bounded repair attempt."""
from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path

from scholar_workflow.analysis.conformance import validate_bundle
from scholar_workflow.analysis.models import (
    AnalysisBatchItem,
    AnalysisBatchRequest,
    AnalysisBatchResult,
    AnalysisDocument,
    AnalysisItemResult,
    AnalysisState,
    ConformanceFinding,
    ConformanceReport,
)
from scholar_workflow.analysis.rendering import AnalysisBundle, render_analysis
from scholar_workflow.analysis.updates import create_baseline

_DDL = """
CREATE TABLE IF NOT EXISTS analysis_batches (
    batch_id TEXT PRIMARY KEY,
    request_fingerprint TEXT NOT NULL,
    state TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS analysis_items (
    batch_id TEXT NOT NULL,
    item_id TEXT NOT NULL,
    zotero_item_key TEXT NOT NULL,
    state TEXT NOT NULL,
    repair_count INTEGER NOT NULL DEFAULT 0 CHECK (repair_count BETWEEN 0 AND 1),
    diagnostics TEXT NOT NULL DEFAULT '[]',
    stage_path TEXT,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (batch_id, item_id),
    FOREIGN KEY (batch_id) REFERENCES analysis_batches(batch_id)
);
CREATE INDEX IF NOT EXISTS idx_analysis_items_state ON analysis_items(state);
"""


class AnalysisBatchConflict(ValueError):
    """A stable batch identity was reused for different input."""


class AnalysisStageSafetyError(ValueError):
    """One item's staging path is unsafe; sibling items may still proceed."""


class AnalysisStageRootError(RuntimeError):
    """The configured staging root changed, so the whole batch must stop."""


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _fingerprint(request: AnalysisBatchRequest) -> str:
    payload = request.model_dump(mode="json")
    payload.pop("batch_id", None)
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return "sha256:" + sha256(encoded.encode()).hexdigest()


class AnalysisBatchStore:
    """State-only SQLite store; it never stores paper text or generated artifacts."""

    def __init__(self, db_path: Path, *, readonly: bool = False) -> None:
        if readonly:
            self._db = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        else:
            db_path.parent.mkdir(parents=True, exist_ok=True)
            self._db = sqlite3.connect(db_path)
            self._db.execute("PRAGMA foreign_keys = ON")
            self._db.executescript(_DDL)
            self._db.commit()
        self._db.execute("PRAGMA busy_timeout = 5000")

    def ensure_batch(self, request: AnalysisBatchRequest) -> None:
        fingerprint = _fingerprint(request)
        now = _now()
        self._db.execute(
            "INSERT OR IGNORE INTO analysis_batches VALUES (?, ?, ?, ?, ?)",
            (request.batch_id, fingerprint, AnalysisState.QUEUED.value, now, now),
        )
        self._db.commit()
        row = self._db.execute(
            "SELECT request_fingerprint FROM analysis_batches WHERE batch_id=?",
            (request.batch_id,),
        ).fetchone()
        if row is None or row[0] != fingerprint:
            raise AnalysisBatchConflict(
                f"batch_id {request.batch_id!r} was reused for a different request"
            )

    def ensure_item(self, batch_id: str, item: AnalysisBatchItem) -> None:
        self._db.execute(
            """
            INSERT OR IGNORE INTO analysis_items
                (batch_id, item_id, zotero_item_key, state, updated_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (batch_id, item.item_id, item.zotero_item_key, AnalysisState.QUEUED.value, _now()),
        )
        self._db.commit()

    def claim_item(self, batch_id: str, item_id: str) -> AnalysisItemResult:
        """Atomically claim one queued item so two runners cannot share its stage."""
        try:
            self._db.execute("BEGIN IMMEDIATE")
            cursor = self._db.execute(
                """
                UPDATE analysis_items
                SET state=?, updated_at=?
                WHERE batch_id=? AND item_id=? AND state=?
                """,
                (
                    AnalysisState.RUNNING.value,
                    _now(),
                    batch_id,
                    item_id,
                    AnalysisState.QUEUED.value,
                ),
            )
            if cursor.rowcount != 1:
                row = self._db.execute(
                    "SELECT state FROM analysis_items WHERE batch_id=? AND item_id=?",
                    (batch_id, item_id),
                ).fetchone()
                if row is None:
                    raise KeyError(f"unknown analysis item {batch_id}/{item_id}")
                raise AnalysisBatchConflict(
                    f"analysis item {batch_id}/{item_id} cannot be claimed from {row[0]}"
                )
            self._db.commit()
        except Exception:
            self._db.rollback()
            raise
        claimed = self.get_item(batch_id, item_id)
        assert claimed is not None
        return claimed

    def update_item(
        self,
        batch_id: str,
        item_id: str,
        state: AnalysisState,
        *,
        repair_count: int | None = None,
        diagnostics: list[ConformanceFinding] | None = None,
        stage_path: str | None = None,
    ) -> None:
        current = self.get_item(batch_id, item_id)
        if current is None:
            raise KeyError(f"unknown analysis item {batch_id}/{item_id}")
        next_repair_count = current.repair_count if repair_count is None else repair_count
        if not 0 <= next_repair_count <= 1:
            raise ValueError("repair_count cannot exceed one")
        payload = current.diagnostics if diagnostics is None else diagnostics
        self._db.execute(
            """
            UPDATE analysis_items
            SET state=?, repair_count=?, diagnostics=?, stage_path=?, updated_at=?
            WHERE batch_id=? AND item_id=?
            """,
            (
                state.value,
                next_repair_count,
                json.dumps([item.model_dump(mode="json") for item in payload]),
                stage_path,
                _now(),
                batch_id,
                item_id,
            ),
        )
        self._db.commit()

    def get_item(self, batch_id: str, item_id: str) -> AnalysisItemResult | None:
        row = self._db.execute(
            """
            SELECT item_id, state, repair_count, diagnostics, stage_path
            FROM analysis_items WHERE batch_id=? AND item_id=?
            """,
            (batch_id, item_id),
        ).fetchone()
        if row is None:
            return None
        return AnalysisItemResult(
            item_id=row[0],
            state=AnalysisState(row[1]),
            repair_count=row[2],
            diagnostics=[
                ConformanceFinding.model_validate(item) for item in json.loads(row[3])
            ],
            stage_path=row[4],
        )

    def list_items(self) -> list[tuple[str, AnalysisItemResult]]:
        """Return state-only rows for an explicit, read-only maintenance audit."""
        rows = self._db.execute(
            """
            SELECT batch_id, item_id, state, repair_count, diagnostics, stage_path
            FROM analysis_items ORDER BY batch_id, item_id
            """
        ).fetchall()
        return [
            (
                row[0],
                AnalysisItemResult(
                    item_id=row[1],
                    state=AnalysisState(row[2]),
                    repair_count=row[3],
                    diagnostics=[
                        ConformanceFinding.model_validate(item)
                        for item in json.loads(row[4])
                    ],
                    stage_path=row[5],
                ),
            )
            for row in rows
        ]

    def update_batch_state(self, batch_id: str, state: str) -> None:
        self._db.execute(
            "UPDATE analysis_batches SET state=?, updated_at=? WHERE batch_id=?",
            (state, _now(), batch_id),
        )
        self._db.commit()

    def close(self) -> None:
        self._db.close()


Renderer = Callable[[AnalysisDocument, str], AnalysisBundle]
Repairer = Callable[[AnalysisDocument, ConformanceReport], AnalysisDocument]


def _default_renderer(document: AnalysisDocument, note_stem: str) -> AnalysisBundle:
    return render_analysis(document, note_stem=note_stem)


def _validate_targeted_repair(
    original: AnalysisDocument,
    repaired: AnalysisDocument,
    report: ConformanceReport,
) -> None:
    if (
        repaired.artifact_id != original.artifact_id
        or repaired.profile != original.profile
        or repaired.paper_title != original.paper_title
    ):
        raise ValueError(
            "targeted repair cannot change artifact identity, profile, or paper title"
        )
    original_claims = {claim.claim_id: claim for claim in original.claims}
    repaired_claims = {claim.claim_id: claim for claim in repaired.claims}
    if set(original_claims) != set(repaired_claims):
        raise ValueError("targeted repair cannot add or remove claims")
    repairable_claim_ids = {
        parts[2]
        for finding in report.findings
        if finding.repairable
        and len(parts := finding.path.split("/")) == 3
        and parts[0] in {"markdown", "canvas"}
        and parts[1] == "claims"
        and parts[2]
    }
    for claim_id, repaired_claim in repaired_claims.items():
        original_claim = original_claims[claim_id]
        if (
            repaired_claim.role != original_claim.role
            or repaired_claim.order != original_claim.order
        ):
            raise ValueError("targeted repair cannot change claim roles or workflow order")
        if repaired_claim != original_claim and claim_id not in repairable_claim_ids:
            raise ValueError(
                f"targeted repair changed claim {claim_id!r} outside reported findings"
            )


class AnalysisBatchRunner:
    def __init__(
        self,
        *,
        store: AnalysisBatchStore,
        stage_root: Path,
        renderer: Renderer = _default_renderer,
    ) -> None:
        self.store = store
        configured_root = stage_root.absolute()
        if configured_root.is_symlink():
            raise ValueError("analysis stage root cannot be a symlink")
        configured_root.mkdir(parents=True, exist_ok=True)
        self.stage_root = configured_root.resolve(strict=True)
        metadata = self.stage_root.stat()
        self._stage_root_identity = (metadata.st_dev, metadata.st_ino)
        self.renderer = renderer

    def _assert_stage_root(self) -> None:
        if self.stage_root.is_symlink() or not self.stage_root.is_dir():
            raise AnalysisStageRootError("analysis stage root is missing or unsafe")
        metadata = self.stage_root.stat()
        if (metadata.st_dev, metadata.st_ino) != self._stage_root_identity:
            raise AnalysisStageRootError("analysis stage root identity changed")

    def _assert_safe_stage_path(self, stage_dir: Path) -> None:
        self._assert_stage_root()
        try:
            relative = stage_dir.relative_to(self.stage_root)
        except ValueError as exc:
            raise AnalysisStageSafetyError(
                "analysis stage path escaped its configured root"
            ) from exc
        if len(relative.parts) != 2 or any(
            part in {"", ".", ".."} or Path(part).name != part
            for part in relative.parts
        ):
            raise AnalysisStageSafetyError(
                "analysis stage path must contain one batch and one item component"
            )
        current = self.stage_root
        for part in relative.parts:
            current /= part
            if current.is_symlink():
                raise AnalysisStageSafetyError(
                    "analysis stage path cannot traverse a symlink"
                )
            if current.exists() and not current.is_dir():
                raise AnalysisStageSafetyError(
                    "analysis stage path component must be a directory"
                )

    def _stage_dir(self, batch_id: str, item_id: str) -> Path:
        target = self.stage_root / batch_id / item_id
        self._assert_safe_stage_path(target)
        return target

    def _clear_owned_stage(self, stage_dir: Path) -> None:
        self._assert_safe_stage_path(stage_dir)
        if not stage_dir.exists():
            return
        allowed = {
            "analysis.md",
            "analysis.canvas",
            "analysis.baseline.json",
            ".analysis.md.tmp",
            ".analysis.canvas.tmp",
            ".analysis.baseline.json.tmp",
        }
        children = list(stage_dir.iterdir())
        unexpected = [child.name for child in children if child.name not in allowed]
        if unexpected:
            raise AnalysisStageSafetyError(
                f"analysis stage contains unowned files: {unexpected}"
            )
        for child in children:
            if child.is_symlink() or not child.is_file():
                raise AnalysisStageSafetyError(
                    "analysis stage cleanup encountered an unsafe entry"
                )
            child.unlink()
        stage_dir.rmdir()
        parent = stage_dir.parent
        if parent != self.stage_root and parent.exists() and not any(parent.iterdir()):
            parent.rmdir()

    def _write_stage(self, stage_dir: Path, bundle: AnalysisBundle) -> None:
        self._assert_safe_stage_path(stage_dir)
        stage_dir.mkdir(parents=True, exist_ok=True)
        self._assert_safe_stage_path(stage_dir)
        files = {
            "analysis.md": bundle.markdown,
            "analysis.canvas": json.dumps(bundle.canvas, ensure_ascii=False, indent=2) + "\n",
        }
        for name, content in files.items():
            target = stage_dir / name
            temporary = stage_dir / f".{name}.tmp"
            temporary.write_text(content, encoding="utf-8")
            temporary.replace(target)

    def _write_baseline(
        self,
        stage_dir: Path,
        document: AnalysisDocument,
        bundle: AnalysisBundle,
        note_stem: str,
    ) -> None:
        baseline = create_baseline(document, bundle, note_stem=note_stem)
        target = stage_dir / "analysis.baseline.json"
        temporary = stage_dir / ".analysis.baseline.json.tmp"
        temporary.write_text(
            baseline.model_dump_json(indent=2) + "\n",
            encoding="utf-8",
        )
        temporary.replace(target)

    def _run_item(
        self,
        batch_id: str,
        item: AnalysisBatchItem,
        repair: Repairer | None,
    ) -> AnalysisItemResult:
        self.store.ensure_item(batch_id, item)
        current = self.store.get_item(batch_id, item.item_id)
        assert current is not None
        if current.state in {
            AnalysisState.VALIDATED,
            AnalysisState.REPAIRED,
            AnalysisState.FAILED,
        }:
            return current

        stage_dir = self.stage_root / batch_id / item.item_id
        try:
            self._assert_safe_stage_path(stage_dir)
            self.store.claim_item(batch_id, item.item_id)
            self._clear_owned_stage(stage_dir)
            bundle = self.renderer(item.document, item.note_stem)
            self._write_stage(stage_dir, bundle)
            report = validate_bundle(item.document, bundle, note_stem=item.note_stem)
            if report.ok:
                self._write_baseline(
                    stage_dir,
                    item.document,
                    bundle,
                    item.note_stem,
                )
                self.store.update_item(
                    batch_id,
                    item.item_id,
                    AnalysisState.VALIDATED,
                    diagnostics=report.findings,
                    stage_path=str(stage_dir),
                )
                return self.store.get_item(batch_id, item.item_id)  # type: ignore[return-value]

            if repair is not None and current.repair_count == 0 and all(
                finding.repairable for finding in report.findings
            ):
                # Claim the one permitted repair before invoking untrusted/model-owned
                # repair code.  A crash or exception can therefore never reset the
                # budget and silently start a second repair in the same batch.
                self.store.update_item(
                    batch_id,
                    item.item_id,
                    AnalysisState.RUNNING,
                    repair_count=1,
                    diagnostics=report.findings,
                    stage_path=str(stage_dir),
                )
                repaired = repair(item.document, report)
                _validate_targeted_repair(item.document, repaired, report)
                bundle = self.renderer(repaired, item.note_stem)
                self._write_stage(stage_dir, bundle)
                report = validate_bundle(repaired, bundle, note_stem=item.note_stem)
                if report.ok:
                    self._write_baseline(
                        stage_dir,
                        repaired,
                        bundle,
                        item.note_stem,
                    )
                    self.store.update_item(
                        batch_id,
                        item.item_id,
                        AnalysisState.REPAIRED,
                        repair_count=1,
                        diagnostics=report.findings,
                        stage_path=str(stage_dir),
                    )
                    return self.store.get_item(batch_id, item.item_id)  # type: ignore[return-value]

            current = self.store.get_item(batch_id, item.item_id)
            assert current is not None
            self.store.update_item(
                batch_id,
                item.item_id,
                AnalysisState.RUNNING,
                repair_count=current.repair_count,
                diagnostics=report.findings,
                stage_path=str(stage_dir),
            )
            self._clear_owned_stage(stage_dir)
            self.store.update_item(
                batch_id,
                item.item_id,
                AnalysisState.FAILED,
                repair_count=current.repair_count,
                diagnostics=report.findings,
                stage_path=None,
            )
        except (sqlite3.Error, AnalysisStageRootError):
            # A state-database failure or loss of the configured root invalidates
            # the whole run; do not misreport it as one paper's conformance result.
            raise
        except Exception as exc:  # noqa: BLE001 - isolate per-item safety/model failures
            cleanup_detail = ""
            current = self.store.get_item(batch_id, item.item_id)
            assert current is not None
            diagnostic = ConformanceFinding(
                code="batch-item-error",
                path=f"items/{item.item_id}",
                message=str(exc),
                repairable=False,
            )
            self.store.update_item(
                batch_id,
                item.item_id,
                AnalysisState.RUNNING,
                repair_count=current.repair_count,
                diagnostics=[diagnostic],
                stage_path=(
                    str(stage_dir)
                    if stage_dir.exists() or stage_dir.is_symlink()
                    else None
                ),
            )
            try:
                self._clear_owned_stage(stage_dir)
            except (OSError, AnalysisStageSafetyError) as cleanup_exc:
                cleanup_detail = f"; staging cleanup also failed: {cleanup_exc}"
            current = self.store.get_item(batch_id, item.item_id)
            assert current is not None
            if cleanup_detail:
                diagnostic = diagnostic.model_copy(
                    update={"message": f"{diagnostic.message}{cleanup_detail}"}
                )
            self.store.update_item(
                batch_id,
                item.item_id,
                AnalysisState.FAILED,
                repair_count=current.repair_count,
                diagnostics=[diagnostic],
                stage_path=(
                    str(stage_dir)
                    if stage_dir.exists() or stage_dir.is_symlink()
                    else None
                ),
            )
        result = self.store.get_item(batch_id, item.item_id)
        assert result is not None
        return result

    def run(
        self,
        request: AnalysisBatchRequest,
        *,
        repair: Repairer | None = None,
    ) -> AnalysisBatchResult:
        self.store.ensure_batch(request)
        results = [self._run_item(request.batch_id, item, repair) for item in request.items]
        succeeded = sum(
            result.state in {AnalysisState.VALIDATED, AnalysisState.REPAIRED}
            for result in results
        )
        if succeeded == len(results):
            state = "completed"
        elif succeeded:
            state = "partial"
        else:
            state = "failed"
        self.store.update_batch_state(request.batch_id, state)
        return AnalysisBatchResult(batch_id=request.batch_id, state=state, items=results)
