"""Recover host identity without silently acknowledging an editor save."""
# ruff: noqa: F811 - imported pytest fixture injection
from __future__ import annotations

import json
from hashlib import sha256

import pytest
from click.testing import CliRunner

from scholar_workflow.analysis.apply_changes import load_knowledge_provider_snapshot
from scholar_workflow.analysis.editor_metadata import acknowledge_canvas_metadata
from scholar_workflow.analysis.models import AnalysisBaseline, AnalysisCommitRequest
from scholar_workflow.cli import main
from scholar_workflow.knowledge.fields import FieldRegistryError
from scholar_workflow.workflows.knowledge_rebinding import rebind, rebind_plan
from scholar_workflow.workflows.knowledge_reproduction import reproduction_plan
from tests.contract.test_knowledge_rebinding import (
    canvas_scope,  # noqa: F401
    files,
    scope,  # noqa: F401
    stale,
)


def editor_save(root, paths, *, change=None):
    path = root / paths['canvas']
    graph = json.loads(path.read_bytes())
    graph['metadata'] = {'version': '1.0-1.0', 'frontmatter': {}}
    if change == 'text':
        next(n for n in graph['nodes'] if n['type'] == 'text')['text'] += ' changed'
    elif change == 'layout':
        graph['nodes'][0]['x'] += 8
    elif change == 'edge':
        edge = graph['edges'][0]
        edge['fromSide'] = 'bottom' if edge.get('fromSide') == 'top' else 'top'
    elif change == 'frontmatter':
        graph['metadata']['frontmatter']['human'] = 'observation'
    elif change == 'unknown':
        graph['metadata']['unknown'] = True
    elif change == 'top-level':
        graph['unknown'] = True
    path.write_text(json.dumps(graph))


def metadata_request(root, paths, provider):
    snapshot = load_knowledge_provider_snapshot(provider)
    baseline = AnalysisBaseline.model_validate_json((root / paths['sidecar']).read_bytes())
    owner = snapshot.manifest.atomic_resources[0]
    return AnalysisCommitRequest.model_validate({
        'commit_id': 'recover-editor-save', 'batch_id': 'recover-editor-save', 'item_id': 'one',
        'source_state': 'validated', 'resource_id': owner.resource_id,
        'note_stem': baseline.note_stem, 'document': baseline.document.model_dump(mode='json'),
        'paths': paths,
        'base_revisions': {p: 'sha256:' + sha256((root / p).read_bytes()).hexdigest()
                           for p in paths.values()},
        'base_catalog_revision': snapshot.catalog.revision,
        'base_snapshot_revision': snapshot.snapshot_revision,
        'zotero_item_key': snapshot.catalog.resources[0].zotero.item_key,
        'relations': [r.model_dump(mode='json') for r in snapshot.relations],
    })


def test_device_recovery_then_explicit_metadata_acknowledgement(canvas_scope):
    root, registry, selection, paths, provider = canvas_scope
    target = stale(provider)
    original = json.loads(target.read_bytes())
    editor_save(root, paths)
    before, state = files(root), files(provider)
    plan = rebind_plan(registry, source_id=selection['source_id'])
    pending = plan['pending_canvas_metadata']
    assert len(pending) == 1 and pending[0]['vault_path'] == paths['canvas']
    assert pending[0]['registered_sha256'] != pending[0]['observed_sha256']
    assert files(root) == before and files(provider) == state
    result = rebind(registry, source_id=selection['source_id'], approved_digest=plan['approved_digest'])
    assert result['status'] == 'binding-restored'
    assert result['pending_canvas_metadata'] == pending
    assert result['file_integrity_verified'] is False
    assert result['file_readset_verified'] is True
    assert json.loads(target.read_bytes())['artifacts'] == original['artifacts']
    assert files(root) == before
    with pytest.raises(FieldRegistryError, match='hash'):
        reproduction_plan(registry, source_id=selection['source_id'])
    assert rebind(registry, source_id=selection['source_id'], approved_digest=plan['approved_digest']) == result
    acknowledged = acknowledge_canvas_metadata(
        vault_root=root, request=metadata_request(root, paths, provider), source_registry=registry,
    )
    assert acknowledged['metadata_only'] is True
    assert files(root) == before
    assert reproduction_plan(registry, source_id=selection['source_id'])['status'] == 'exportable'


@pytest.mark.parametrize('change', ['text', 'layout', 'edge', 'frontmatter', 'unknown', 'top-level'])
def test_non_metadata_changes_still_refuse_without_writes(canvas_scope, change):
    root, registry, selection, paths, provider = canvas_scope
    stale(provider)
    editor_save(root, paths, change=change)
    before, state = files(root), files(provider)
    with pytest.raises((FieldRegistryError, ValueError, RuntimeError)):
        rebind_plan(registry, source_id=selection['source_id'])
    assert files(root) == before and files(provider) == state


@pytest.mark.parametrize('phase', ['prepared', 'provider-rebound'])
def test_metadata_pending_recovery_retries_exact_journal(canvas_scope, phase):
    root, registry, selection, paths, provider = canvas_scope
    stale(provider)
    editor_save(root, paths)
    before = files(root)
    plan = rebind_plan(registry, source_id=selection['source_id'])

    def interrupt(current):
        if current == phase:
            raise RuntimeError('interrupted')

    with pytest.raises(RuntimeError, match='interrupted'):
        rebind(registry, source_id=selection['source_id'], approved_digest=plan['approved_digest'],
               fault_inject=interrupt)
    result = rebind(registry, source_id=selection['source_id'], approved_digest=plan['approved_digest'])
    assert result['pending_canvas_metadata'] == plan['pending_canvas_metadata']
    assert files(root) == before


def test_metadata_change_invalidates_prepared_digest(canvas_scope):
    root, registry, selection, paths, provider = canvas_scope
    target = stale(provider)
    editor_save(root, paths)
    plan = rebind_plan(registry, source_id=selection['source_id'])
    path = root / paths['canvas']
    path.write_bytes(path.read_bytes() + b'\n')
    state = files(provider)
    with pytest.raises(FieldRegistryError, match='inputs changed'):
        rebind(registry, source_id=selection['source_id'], approved_digest=plan['approved_digest'])
    assert files(provider) == state and target.exists()


@pytest.mark.parametrize('member', ['markdown', 'sidecar'])
def test_pending_metadata_does_not_adopt_other_bundle_drift(canvas_scope, member):
    root, registry, selection, paths, provider = canvas_scope
    stale(provider)
    editor_save(root, paths)
    path = root / paths[member]
    path.write_bytes(path.read_bytes() + b'\n')
    before, state = files(root), files(provider)
    with pytest.raises(FieldRegistryError, match='hash'):
        rebind_plan(registry, source_id=selection['source_id'])
    assert files(root) == before and files(provider) == state


def test_plain_serialization_drift_is_not_an_editor_metadata_save(canvas_scope):
    root, registry, selection, paths, provider = canvas_scope
    stale(provider)
    path = root / paths['canvas']
    path.write_bytes(path.read_bytes() + b'\n')
    before, state = files(root), files(provider)
    with pytest.raises(FieldRegistryError):
        rebind_plan(registry, source_id=selection['source_id'])
    assert files(root) == before and files(provider) == state


def test_current_binding_keeps_metadata_pending_without_writing_journal(canvas_scope):
    root, registry, selection, paths, provider = canvas_scope
    editor_save(root, paths)
    before, state = files(root), files(provider)
    plan = rebind_plan(registry, source_id=selection['source_id'])
    assert plan['status'] == 'unchanged' and plan['pending_canvas_metadata']
    result = rebind(registry, source_id=selection['source_id'], approved_digest=plan['approved_digest'])
    assert result['status'] == 'unchanged' and result['pending_canvas_metadata']
    assert files(root) == before and files(provider) == state


@pytest.mark.parametrize('language,expected', [('zh', '仍待确认'), ('en', 'still requires acknowledgement')])
def test_cli_reports_remaining_editor_acknowledgement(canvas_scope, monkeypatch, language, expected):
    root, registry, selection, paths, provider = canvas_scope
    stale(provider)
    editor_save(root, paths)
    monkeypatch.setenv('SCHOLAR_WORKFLOW_HOME', str(registry.path.parent.parent))
    runner = CliRunner()
    args = ['--source-id', selection['source_id'], '--language', language]
    preview = runner.invoke(main, ['knowledge', 'rebind-plan', *args])
    assert preview.exit_code == 0, preview.output
    assert expected in preview.output and paths['canvas'] in preview.output
    plan = rebind_plan(registry, source_id=selection['source_id'])
    result = runner.invoke(main, ['knowledge', 'rebind', *args, '--approved-digest',
                                  plan['approved_digest'], '--yes'])
    assert result.exit_code == 0, result.output
    assert expected in result.output and paths['canvas'] in result.output
