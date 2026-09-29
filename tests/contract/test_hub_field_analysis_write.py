"""The public Field editor cannot bypass validated analysis transactions."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

from scholar_workflow.hub.catalog import StaticCatalogProvider
from scholar_workflow.hub.fields import FieldService, KnowledgeSourceRegistry
from scholar_workflow.hub.models import HubCatalog
from scholar_workflow.hub.server import start_hub_server


def test_v3_field_put_rejects_analysis_but_preserves_plain_markdown_cas(
    tmp_path: Path,
) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    home = vault / "00-领域入口.md"
    home.write_text("# Field\n", encoding="utf-8")
    analysis = vault / "JEPA分析.md"
    analysis.write_text("# JEPA\n", encoding="utf-8")
    service = FieldService(KnowledgeSourceRegistry(tmp_path / "sources.json"))
    preview = service.preview(vault)
    field_id = service.confirm(preview.candidate_token, preview.fields[0].field_id).fields[0].field_id
    (vault / "JEPA解析树.canvas").write_text('{"nodes": [], "edges": []}', encoding="utf-8")
    server = start_hub_server(
        port=0,
        storage_root=tmp_path / "storage",
        vault_root=vault,
        catalog_provider=StaticCatalogProvider(
            HubCatalog(generated_at=datetime(2026, 9, 27, tzinfo=UTC), resources=[])
        ),
        field_service=service,
    )
    try:
        port = server.server_address[1]
        origin = f"http://127.0.0.1:{port}"
        headers = {
            "Origin": origin,
            "Content-Type": "application/json",
            "X-Scholar-Hub-Token": server.runtime.session_token,
        }

        def put(relative_path: str, content: str) -> tuple[int, dict[str, object]]:
            revision = service.read_document(field_id, relative_path)["revision"]
            request = urllib.request.Request(
                f"{origin}/api/v3/fields/{field_id}/documents",
                method="PUT",
                data=json.dumps(
                    {
                        "relative_path": relative_path,
                        "content": content,
                        "base_revision": revision,
                    }
                ).encode("utf-8"),
                headers=headers,
            )
            try:
                with urllib.request.urlopen(request, timeout=3) as response:
                    return response.status, json.load(response)
            except urllib.error.HTTPError as exc:
                return exc.code, json.load(exc)

        status, body = put("JEPA分析.md", "# Silently changed analysis\n")
        assert status == 409
        assert "validated Field transaction" in str(body["error"])
        assert analysis.read_text(encoding="utf-8") == "# JEPA\n"

        status, body = put("00-领域入口.md", "# Updated Field\n")
        assert status == 200
        assert body["ok"] is True
        assert home.read_text(encoding="utf-8") == "# Updated Field\n"
    finally:
        server.shutdown()
        server.server_close()
