# Portable identity for an already-owned analysis Canvas

After paired commit and explicit provider apply, declare the Canvas in its registered
Source's `.scholar-workflow/artifacts.yml`. This is a portable identity/owner declaration,
not a new body, provider, analysis commit, scientific assessment or full cross-host restore.
It needs no Hub service, cmux destination, network or external application.

In an installation supporting these commands:

```text
scholar-workflow knowledge canvas-plan --source-id SOURCE_UUID --field-id FIELD_UUID --artifact-id CANVAS_ID --language en
scholar-workflow knowledge register-canvas --source-id SOURCE_UUID --field-id FIELD_UUID --artifact-id CANVAS_ID --approved-digest HEX_DIGEST
```

Use the explicit Canvas artifact ID returned by the prior analysis/provider receipt.
`canvas-plan --format json` gives the separate machine plan. The default Markdown
describes the selected file, change and confirmation digest. Review it, then confirm
the exact plan. `--yes` is only for an already reviewed explicit digest.

The plan resolves the writable Source and selected Field, unique paper owner, all three
provider artifact declarations and actual file hashes. It checks the existing baseline,
paired format and graph contract. No path or object is discovered from similar filenames.
The resulting row uses Source-relative paths and existing resource/analysis identity;
no host path, reader ID, service port or private Canvas top-level field is introduced.
Only this row is appended; unrelated rows and comments are preserved. Conflicting IDs or
paths, malformed manifests, symlinks, unsupported versions and drift fail closed.

Registration changes only the portable artifact manifest and a host-local recovery journal;
the analysis three-file bundle, Field, registry and provider snapshot are not rewritten.
Changing content still requires the normal paired commit and provider apply, not this command.
After interruption, repeat the same selection and approved digest. Recovery accepts only
the reviewed before/after manifest bytes and unchanged Source/Field/provider/bundle authority.
A human edit stops recovery; do not delete the journal or force an overwrite. A completed
declaration does not authorize a later move, rename, stale provider hash or source rebind.

Existing portable Field attachment registers only host location. This Canvas declaration
does not by itself restore the full paper/provider inventory on another host, reverify PDF
versions, validate native links or certify human visual quality. Report those independently.
