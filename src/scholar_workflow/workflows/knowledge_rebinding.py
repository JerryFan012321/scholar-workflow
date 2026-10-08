"""Explicitly recover a same-directory device-number change without adopting content."""
from __future__ import annotations

import fcntl
import json
import os
import re

from scholar_workflow.analysis.apply_changes import (
    KnowledgeProviderSnapshot,
    _locked_state_root,
    _vault_binding_for_root,
)
from scholar_workflow.analysis.commit import _read_target_regular
from scholar_workflow.knowledge.fields import (
    FieldRegistryError,
    FieldService,
    KnowledgeSourceRegistry,
    _open_directory_chain,
)
from scholar_workflow.workflows.knowledge_reproduction import _inventory
from scholar_workflow.workflows.register_paper import (
    _LIMIT,
    _SNAPSHOT,
    _bytes,
    _hash,
    _identity,
    _pairs,
    _provider_path,
    _put,
    _read,
)


def rebind_plan(registry: KnowledgeSourceRegistry, *, source_id: str) -> dict:
    """Zero-write preview; only an unchanged path/inode can recover its device number."""
    return _plan(registry, source_id=source_id)


def _plan(registry, *, source_id, provider_before=None, before_verify=None):
    root = registry.resolve(source_id, capability='write')
    binding = _vault_binding_for_root(root)
    registry_hash = registry.revision()
    fields = FieldService._load_manifest(root)
    if fields.source_id != source_id:
        raise FieldRegistryError('Portable Source identity differs from registered Source')
    FieldService._validate_manifest_paths(root, fields)
    descriptors = []
    try:
        for folder in (root, root / '.scholar-workflow', _provider_path(registry, source_id)):
            descriptors.append(_open_directory_chain(folder))
        root_fd, state_fd, provider_fd = descriptors
        actual, _ = _read(provider_fd, _SNAPSHOT)
        if actual is None:
            raise FieldRegistryError('Rebinding requires an existing provider')
        before = actual if provider_before is None else provider_before.encode('utf-8')
        snapshot = KnowledgeProviderSnapshot.model_validate(
            json.loads(before, object_pairs_hook=_pairs))
        old = snapshot.vault_binding
        if old is None or old.root_path != str(root) or old.inode != binding.inode:
            raise FieldRegistryError('Device recovery requires the same path and inode')
        data = snapshot.model_dump(mode='json')
        data.update(vault_binding=binding.model_dump(mode='json'), snapshot_revision='')
        after = KnowledgeProviderSnapshot.model_validate(data).model_dump(mode='json')
        if actual not in (before, _bytes(after)):
            raise FieldRegistryError('Provider changed; refusing directory recovery')
        contents, hashes, manifests, _, _ = _inventory(root, root_fd, state_fd, fields, snapshot)
        if before_verify is not None:
            before_verify()
        if (registry.revision() != registry_hash
                or registry.resolve(source_id, capability='write') != root
                or _vault_binding_for_root(root) != binding
                or FieldService._load_manifest(root) != fields
                or _read(provider_fd, _SNAPSHOT)[0] != actual
                or any(_read_target_regular(root, root_fd, name) != payload
                       for name, payload in contents.items())
                or any(_read(state_fd, name)[0] != payload for name, payload in manifests.items())):
            raise FieldRegistryError('Rebinding authority or files changed during inspection')
        for folder, opened in zip((root, root / '.scholar-workflow', _provider_path(registry, source_id)), descriptors):
            current = _open_directory_chain(folder)
            try:
                if _identity(os.fstat(current))[:2] != _identity(os.fstat(opened))[:2]:
                    raise FieldRegistryError('Rebinding directory changed during inspection')
            finally:
                os.close(current)
        plan = {'schema_version': 1, 'source_id': source_id,
                'status': 'unchanged' if old == binding else 'ready',
                'previous_binding': old.model_dump(mode='json'),
                'root_binding': binding.model_dump(mode='json'), 'registry_revision': registry_hash,
                'provider_hash': _hash(before), 'provider_before': before.decode('utf-8'),
                'provider_after': after, 'files': hashes,
                'manifest_hashes': {name: _hash(payload) if payload is not None else None
                                    for name, payload in manifests.items()}}
        plan['approved_digest'] = _hash(_bytes(plan)).removeprefix('sha256:')
        if len(_bytes({'status': 'prepared', 'plan': plan})) > _LIMIT:
            raise FieldRegistryError('Rebinding recovery record exceeds its safe size limit')
        return plan
    finally:
        for descriptor in reversed(descriptors):
            os.close(descriptor)


def rebind(registry: KnowledgeSourceRegistry, *, source_id: str, approved_digest: str,
           fault_inject=None) -> dict:
    """CAS-rebind one reviewed host identity; retain a resumable, digest-bound journal."""
    if re.fullmatch(r'[0-9a-f]{64}', approved_digest) is None:
        raise FieldRegistryError('Approved digest must be SHA-256 hex')
    root = registry.resolve(source_id, capability='write')
    provider_path = _provider_path(registry, source_id)
    # Missing/unsafe roots are not initialized by recovery.
    for folder in (root / '.scholar-workflow', provider_path):
        os.close(_open_directory_chain(folder))
    name = 'knowledge-rebinding-' + approved_digest + '.json'
    with registry._write_guard(), _locked_state_root(provider_path) as provider:
        root_fd = _open_directory_chain(root)
        try:
            fcntl.flock(root_fd, fcntl.LOCK_EX)
            prior, _ = _read(provider.fd, name)
            if prior is None:
                plan = _plan(registry, source_id=source_id)
                if plan['approved_digest'] != approved_digest:
                    raise FieldRegistryError('Rebinding inputs changed; review a new plan')
                journal = {'status': 'prepared', 'plan': plan}
            else:
                journal = json.loads(prior, object_pairs_hook=_pairs)
                if (not isinstance(journal, dict) or set(journal) != {'status', 'plan'}
                        or journal['status'] not in {'prepared', 'committed'}
                        or not isinstance(journal['plan'], dict)):
                    raise FieldRegistryError('Invalid rebinding recovery journal')
                plan = journal['plan']
                semantic = {key: value for key, value in plan.items() if key != 'approved_digest'}
                if (plan.get('approved_digest') != approved_digest
                        or _hash(_bytes(semantic)).removeprefix('sha256:') != approved_digest):
                    raise FieldRegistryError('Rebinding journal digest differs from approval')
                if plan.get('source_id') != source_id:
                    raise FieldRegistryError('Rebinding journal belongs to another Source')
            before, after = plan['provider_before'].encode(), _bytes(plan['provider_after'])

            def verify():
                provider.ensure_current()
                if _identity(os.fstat(root_fd))[:2] != (
                    plan['root_binding']['device'], plan['root_binding']['inode']
                ) or _plan(registry, source_id=source_id,
                           provider_before=plan['provider_before']) != plan:
                    raise FieldRegistryError('Rebinding inputs changed; review a new plan')

            verify()
            result = {'schema_version': 1, 'source_id': source_id,
                      'status': 'unchanged' if plan['status'] == 'unchanged' else 'binding-restored',
                      'receipt_id': 'knowledge-rebinding:' + approved_digest,
                      'approved_digest': approved_digest,
                      'snapshot_revision': plan['provider_after']['snapshot_revision'],
                      'catalog_revision': plan['provider_after']['catalog']['revision'],
                      'content_rewritten': False, 'file_integrity_verified': True,
                      'source_verified': False, 'human_verified': False, 'backup_verified': False}
            if journal['status'] == 'committed':
                if _read(provider.fd, _SNAPSHOT)[0] != after:
                    raise FieldRegistryError('Rebound provider changed after completion')
                return result
            if plan['status'] == 'unchanged':
                return result
            if prior is None:
                _put(provider.fd, name, None, _bytes(journal))
            if fault_inject:
                fault_inject('prepared')
            verify()
            _put(provider.fd, _SNAPSHOT, before, after)
            if fault_inject:
                fault_inject('provider-rebound')
            verify()
            current, _ = _read(provider.fd, name)
            if current != _bytes(journal):
                raise FieldRegistryError('Rebinding journal changed during publication')
            _put(provider.fd, name, current, _bytes(dict(journal, status='committed')))
            return result
        finally:
            fcntl.flock(root_fd, fcntl.LOCK_UN)
            os.close(root_fd)
