"""Device-number recovery never adopts a different directory or content drift."""
# ruff: noqa: F811 - imported pytest fixture injection
from __future__ import annotations

import json

import pytest
from click.testing import CliRunner

from scholar_workflow.analysis.apply_changes import KnowledgeProviderSnapshot
from scholar_workflow.cli import main
from scholar_workflow.knowledge.fields import FieldRegistryError
from scholar_workflow.workflows.knowledge_rebinding import _plan, rebind, rebind_plan
from scholar_workflow.workflows.knowledge_reproduction import reproduction_plan
from tests.contract.test_canvas_registration import canvas_scope  # noqa: F401
from tests.contract.test_knowledge_reproduction_assets import selected_canvas_scope  # noqa: F401
from tests.contract.test_paper_registration import scope  # noqa: F401


def files(root):
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob('*') if p.is_file()}


def stale(provider, **changes):
    target = provider / 'knowledge-provider.snapshot.json'
    data = json.loads(target.read_bytes())
    data['vault_binding'].update(device=data['vault_binding']['device'] + 2, **changes)
    data['snapshot_revision'] = ''
    target.write_text(json.dumps(KnowledgeProviderSnapshot.model_validate(data).model_dump(mode='json'),
                               ensure_ascii=False, sort_keys=True, indent=2) + '\n')
    return target


def test_zero_write_preview_and_only_binding_changes(canvas_scope):
    root, registry, selection, _, provider = canvas_scope
    target = stale(provider)
    before, state = files(root), files(provider)
    original = json.loads(target.read_bytes())
    with pytest.raises(FieldRegistryError, match='another Source root'):
        reproduction_plan(registry, source_id=selection['source_id'])
    plan = rebind_plan(registry, source_id=selection['source_id'])
    assert plan == rebind_plan(registry, source_id=selection['source_id'])
    assert files(root) == before and files(provider) == state
    receipt = rebind(registry, source_id=selection['source_id'], approved_digest=plan['approved_digest'])
    assert receipt['status'] == 'binding-restored' and not receipt['content_rewritten']
    after = json.loads(target.read_bytes())
    assert after.pop('vault_binding') == plan['root_binding']
    original.pop('vault_binding')
    assert after.pop('snapshot_revision') != original.pop('snapshot_revision')
    assert after == original
    assert files(root) == before
    assert reproduction_plan(registry, source_id=selection['source_id'])['status'] == 'exportable'
    assert rebind(registry, source_id=selection['source_id'], approved_digest=plan['approved_digest']) == receipt
    assert rebind_plan(registry, source_id=selection['source_id'])['status'] == 'unchanged'


@pytest.mark.parametrize('member', ['markdown', 'canvas', 'sidecar', 'fields', 'registry', 'provider'])
def test_changed_reviewed_readset_refuses_without_rebinding(canvas_scope, member):
    root, registry, selection, paths, provider = canvas_scope
    target = stale(provider)
    plan = rebind_plan(registry, source_id=selection['source_id'])
    file = (root / paths[member] if member in paths else registry.path if member == 'registry'
            else target if member == 'provider' else root / '.scholar-workflow/fields.yml')
    file.write_bytes(file.read_bytes() + b'\n')
    before = target.read_bytes()
    with pytest.raises((FieldRegistryError, OSError, ValueError)):
        rebind(registry, source_id=selection['source_id'], approved_digest=plan['approved_digest'])
    assert target.read_bytes() == before


@pytest.mark.parametrize('change', ['path', 'inode'])
def test_different_directory_is_not_device_recovery(canvas_scope, change):
    root, registry, selection, _, provider = canvas_scope
    changes = {'root_path': str(root.parent)} if change == 'path' else {'inode': root.stat().st_ino + 1}
    target = stale(provider, **changes)
    before = target.read_bytes()
    with pytest.raises(FieldRegistryError, match='same path and inode'):
        rebind_plan(registry, source_id=selection['source_id'])
    assert target.read_bytes() == before


@pytest.mark.parametrize('phase', ['prepared', 'provider-rebound'])
def test_interruption_reuses_exact_journal(canvas_scope, phase):
    root, registry, selection, _, provider = canvas_scope
    stale(provider)
    before = files(root)
    plan = rebind_plan(registry, source_id=selection['source_id'])
    def stop(current):
        if current == phase:
            raise RuntimeError('interrupted')
    with pytest.raises(RuntimeError, match='interrupted'):
        rebind(registry, source_id=selection['source_id'], approved_digest=plan['approved_digest'], fault_inject=stop)
    assert rebind(registry, source_id=selection['source_id'], approved_digest=plan['approved_digest'])['status'] == 'binding-restored'
    assert files(root) == before


def test_journal_tampering_is_not_an_approval(canvas_scope):
    _, registry, selection, _, provider = canvas_scope
    target = stale(provider)
    plan = rebind_plan(registry, source_id=selection['source_id'])
    def stop(_):
        raise RuntimeError('interrupted')
    with pytest.raises(RuntimeError):
        rebind(registry, source_id=selection['source_id'], approved_digest=plan['approved_digest'], fault_inject=stop)
    journal = provider / ('knowledge-rebinding-' + plan['approved_digest'] + '.json')
    data = json.loads(journal.read_bytes())
    data['plan']['root_binding']['inode'] += 1
    journal.write_text(json.dumps(data))
    before = target.read_bytes()
    with pytest.raises(FieldRegistryError, match='digest'):
        rebind(registry, source_id=selection['source_id'], approved_digest=plan['approved_digest'])
    assert target.read_bytes() == before


def test_symlink_and_asset_drift_refuse(selected_canvas_scope):
    root, registry, selection, rows, _ = selected_canvas_scope
    provider = registry.path.parent / 'knowledge-providers' / selection['source_id']
    target = stale(provider)
    asset = root / rows[0]['vault_path']
    plan = rebind_plan(registry, source_id=selection['source_id'])
    asset.write_bytes(asset.read_bytes() + b'drift')
    before = target.read_bytes()
    with pytest.raises(FieldRegistryError, match='asset'):
        rebind(registry, source_id=selection['source_id'], approved_digest=plan['approved_digest'])
    asset.rename(asset.with_suffix('.original'))
    asset.symlink_to(asset.with_suffix('.original'))
    with pytest.raises((FieldRegistryError, OSError, ValueError)):
        rebind_plan(registry, source_id=selection['source_id'])
    assert target.read_bytes() == before


@pytest.mark.parametrize('field,value', [('enabled', False), ('capabilities', ['read'])])
def test_disabled_readonly_registry_refuses(canvas_scope, field, value):
    _, registry, selection, _, provider = canvas_scope
    target = stale(provider)
    data = json.loads(registry.path.read_bytes())
    data['sources'][0][field] = value
    registry.path.write_text(json.dumps(data))
    before = files(provider)
    with pytest.raises(FieldRegistryError):
        rebind_plan(registry, source_id=selection['source_id'])
    assert files(provider) == before and target.exists()


def test_cli_requires_review_and_human_result_stays_honest(canvas_scope, monkeypatch):
    _, registry, selection, _, provider = canvas_scope
    stale(provider)
    monkeypatch.setenv('SCHOLAR_WORKFLOW_HOME', str(registry.path.parent.parent))
    runner = CliRunner()
    args = ['--source-id', selection['source_id']]
    planned = runner.invoke(main, ['knowledge', 'rebind-plan', *args, '--format', 'json'])
    assert planned.exit_code == 0, planned.output
    plan = json.loads(planned.output)
    refused = runner.invoke(main, ['knowledge','rebind',*args,'--approved-digest','0'*64,'--yes'])
    assert refused.exit_code == 7
    result = runner.invoke(main, ['knowledge','rebind',*args,'--approved-digest',plan['approved_digest'],'--yes','--language','zh'])
    assert result.exit_code == 0, result.output
    assert '绑定已恢复' in result.output and '正文' in result.output
    assert '不是已验证备份' in result.output


def test_unchanged_cli_result_does_not_claim_recovery(canvas_scope, monkeypatch):
    root, registry, selection, _, provider = canvas_scope
    monkeypatch.setenv('SCHOLAR_WORKFLOW_HOME', str(registry.path.parent.parent))
    plan = rebind_plan(registry, source_id=selection['source_id'])
    before, state = files(root), files(provider)
    result = CliRunner().invoke(main, ['knowledge', 'rebind', '--source-id', selection['source_id'],
                                     '--approved-digest', plan['approved_digest'], '--yes',
                                     '--language', 'zh'])
    assert result.exit_code == 0, result.output
    assert '无需改变' in result.output and '已恢复' not in result.output
    assert files(root) == before and files(provider) == state


@pytest.mark.parametrize('digest', ['bad', 'A' * 64])
def test_invalid_digest_does_not_create_journal(canvas_scope, digest):
    _, registry, selection, _, provider = canvas_scope
    before = files(provider)
    with pytest.raises(FieldRegistryError, match='SHA-256'):
        rebind(registry, source_id=selection['source_id'], approved_digest=digest)
    assert files(provider) == before


def test_unknown_source_never_creates_provider(canvas_scope):
    root, registry, _, _, provider = canvas_scope
    before, state = files(root), files(provider)
    with pytest.raises(FieldRegistryError):
        rebind_plan(registry, source_id='00000000-0000-0000-0000-000000000000')
    assert files(root) == before and files(provider) == state


def test_plain_navigation_note_is_in_reviewed_readset(canvas_scope):
    root, registry, selection, _, provider = canvas_scope
    target = stale(provider)
    plan = rebind_plan(registry, source_id=selection['source_id'])
    assert 'README.md' in plan['files']
    (root / 'README.md').write_text('Concurrent human edit\n')
    before = target.read_bytes()
    with pytest.raises(FieldRegistryError, match='inputs changed'):
        rebind(registry, source_id=selection['source_id'], approved_digest=plan['approved_digest'])
    assert target.read_bytes() == before


@pytest.mark.parametrize('location', ['root', 'provider'])
def test_symlink_directory_refused(canvas_scope, location):
    root, registry, selection, _, provider = canvas_scope
    stale(provider)
    path = root if location == 'root' else provider
    original = path.with_name(path.name + '-original')
    path.rename(original)
    path.symlink_to(original, target_is_directory=True)
    before = files(original)
    with pytest.raises((FieldRegistryError, OSError, ValueError)):
        rebind_plan(registry, source_id=selection['source_id'])
    assert files(original) == before


def test_concurrent_edit_during_preview_refused(canvas_scope):
    root, registry, selection, _, provider = canvas_scope
    target = stale(provider)
    before = target.read_bytes()
    def edit():
        (root / 'README.md').write_text('Concurrent edit\n')
    with pytest.raises(FieldRegistryError, match='changed during inspection'):
        _plan(registry, source_id=selection['source_id'], before_verify=edit)
    assert target.read_bytes() == before


def test_concurrent_root_replacement_refused(canvas_scope):
    root, registry, selection, _, provider = canvas_scope
    target = stale(provider)
    before = target.read_bytes()
    def replace():
        root.rename(root.with_name(root.name + '-old'))
        root.mkdir()
    with pytest.raises((FieldRegistryError, OSError, ValueError)):
        _plan(registry, source_id=selection['source_id'], before_verify=replace)
    assert target.read_bytes() == before


def test_edit_after_preparation_never_overwritten(canvas_scope):
    root, registry, selection, _, provider = canvas_scope
    target = stale(provider)
    plan = rebind_plan(registry, source_id=selection['source_id'])
    before = target.read_bytes()
    def edit(phase):
        if phase == 'prepared':
            (root / 'README.md').write_text('Concurrent human edit\n')
    with pytest.raises(FieldRegistryError, match='inputs changed'):
        rebind(registry, source_id=selection['source_id'], approved_digest=plan['approved_digest'],
               fault_inject=edit)
    assert target.read_bytes() == before
    assert (root / 'README.md').read_text() == 'Concurrent human edit\n'
