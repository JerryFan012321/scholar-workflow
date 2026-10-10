# Field references: independent schema and reproduction expectations

Prepared before implementation. The companion tests have not been executed. This
is a contract for portable metadata, not permission to write a real Field or claim
that an external target exists. Inputs are dictionaries and pytest-only Sources.

## Fixed representation

`FieldManifest.schema_version = 2` permits `references` on each Field:

```json
{
  "reference_id": "ref:external-paper",
  "target": {
    "source_id": "abcdefab-cdef-4abc-8def-abcdefabcdef",
    "object_id": "paper:zotero:123:JKLM2345"
  },
  "purpose": "Compare this existing paper in the selected research context."
}
```

- `reference_id`: lowercase portable ID, length 2..128, pattern
  `^[a-z0-9][a-z0-9._:-]{1,127}$`.
- `object_id`: stable opaque ID, length 1..256, pattern
  `^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$`; never a path or reader URL.
- `source_id`: canonical lowercase hyphenated UUID.
- `purpose`: clean, nonempty text, length 1..2000; no leading/trailing whitespace
  or control characters. Missing/null purposes are invalid.
- At most 512 records per Field. Within one Field, `reference_id` is unique and
  `(target.source_id, target.object_id)` is unique. The same `object_id` qualified
  by different Source IDs is structurally distinct; actual owner conflicts belong
  to the resolver, not this syntax validator.
- Unknown fields, embedded absolute/relative paths and arbitrary URLs are refused.

## Hand-written cases

| Case | Expected result |
|---|---|
| V1 | Schema 1 without references accepts and dumps exactly the old dictionary/JSON shape; no extra empty references fields |
| V2 | Schema 1 explicitly containing `references: []` or nonempty references refuses; no silent schema upgrade |
| V3 | Schema 2 retains the exact qualified target, ID and purpose; local navigation/home remain unchanged |
| V4 | One Field with duplicate reference IDs or duplicate qualified targets refuses |
| V5 | Distinct Source IDs for the same object ID accept syntactically; one ID/target may also be reused in another Field |
| V6 | 512 distinct references accept; 513 refuse |
| V7 | Unknown/negative/boolean/string schema versions, malformed/noncanonical UUIDs, invalid IDs and absent/dirty/oversized purposes refuse |
| V8 | Extra path/URL fields at reference or target level refuse; neither stable identity field accepts a path/URL |
| J1 | The public reproduction schema's embedded Field mapping accepts old schema 1 and valid schema 2, rejects schema 1 references and schema 3 |
| R1 | Existing synthetic paper/analysis/Canvas inventory exports a schema 2 Field reference; the whole package survives JSON serialization and package loading with the exact reference metadata |
| R2 | Export changes no Source/provider/registry bytes. Its inventory hashes the actual schema 2 fields.yml bytes, preserves navigation, and does not create an external owner, include an external body or copy an external paper |
| A1 | A reference does not add its target to local navigation or expand `read_document`/`write_document` authorization; an existing undeclared Markdown file still refuses read/write |

## Scope and oracle

Assertions use independently written dictionaries, JSON/YAML inspection and stdlib
SHA-256 of fixture bytes. Production validators are exercised as the subject under
test, not used to manufacture expected records or hashes. The reproduction case
reuses the established synthetic `canvas_scope` fixture only for an existing owned
bundle; it writes schema 2 metadata directly in that pytest root as test setup and
does not depend on a future Field-reference writer or execute restoration.

No real Vault, Zotero library, application, network, runtime installation, release,
paper analysis or migration is involved. Acceptance of the syntax does not verify
the target's existence, ownership uniqueness, scientific content or reader URI.
