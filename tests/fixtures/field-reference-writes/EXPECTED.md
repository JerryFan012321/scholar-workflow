# Independent Field reference write expectations

- A reference selects an existing object; no provider, owner, body, Canvas or PDF is written.
- A plan creates no file, lock or directory and is stable for unchanged inputs.
- Adding a qualified object requires one globally verifiable owner and available object/primary files.
- A repeated identical add is unchanged; ID replacement and duplicate target are refused.
- Removing an exact local reference does not require its target to be registered or online.
- Schema 1 upgrades on add, schema 2 never downgrades on remove; unrelated Fields,
  navigation, references and YAML comments survive.
- Stale registry, manifest, provider, file metadata, folder binding or unsafe symlinks
  invalidate approval. No stale digest overwrites the present manifest.
- A publication interruption leaves a whole old or new manifest. A fresh plan observes
  the actual state; an old approval is not a recovery license.
- Human output describes the selected Field, action, purpose and unchanged source
  content without absolute paths or raw object IDs; JSON retains machine identities.
- Human removal previews identify the selected local reference name even when two
  records have the same purpose; they never display the other reference as selected.
- CLI confirmation cancellation writes nothing; safety refusal exits 7.
