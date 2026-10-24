# ingest-resource

Import papers and archive technical documents through Zotero's Local API.
A paper's metadata comes from an authoritative web source, never from the PDF;
an available PDF comes from arXiv. Metadata-only cases retain their missing-PDF reason.
Three acquisition phases:

- **Existence check (read-only)** — normalize the identifier (DOI / title+authors;
  arXiv id is a download-source label, not an identity), then search and confirm through
  `scholar-workflow zotero`. Outcome is exact / conflict / none. The `zotero ingest`
  command repeats the exact check immediately before create.
- **Acquire metadata (read-only web fetch)** — for new items, read metadata from arXiv
  abs / CVF / DBLP / publisher. When a published version exists, its venue overrides the
  arXiv "preprint" label. Don't fabricate missing secondary fields.
- **Write (via Local API)** — ask which collection the paper belongs to, download the
  arXiv PDF into `paper_inbox`, then pass metadata, collection keys, and the PDF path to
  `scholar-workflow zotero ingest`. Additive writes proceed under the user's standing
  instruction; only delete/overwrite/merge need approval. Technical documents are copied
  into the Vault with source/hash metadata.

Downloaded PDFs go only to `paper_inbox`; technical documents only to the Vault. All
Zotero access is via its loopback Local API — the plugin never writes `zotero.sqlite`.

## A selected official webpage or blog

When the requested source is an official webpage rather than a paper, keep it as a
real Zotero `webpage` / `blogPost` bibliography without inventing a PDF. If the user
also requests a source snapshot, register the authorized original Markdown in the
selected Source/Field as `resources/<stable-segment>/Source.md`. The installed
`knowledge document-plan` and `register-document` commands bind its item identity,
URL, retrieval time, source-block anchors and hash through a reviewed digest and
recoverable transaction. See the [document registration contract](../../references/document-registration.md)
for inputs, commands, conflicts and handoff.

Bibliographic creation, source registration and a later paired analysis have separate
results. This branch does not download a paper from a non-arXiv source or turn an
announcement into a complete technical report. A public image/text URL is not an
open license; preserve the source's reuse restrictions and extraction gaps.

## When the request includes a reading index

Import, collection membership, Knowledge owner registration and index update have
separate completion evidence. Finish the requested parts in the selected existing
format, read back the result, and report remaining gaps. A stale list does not justify
reimporting an existing paper. Import-only requests do not create a Field or index.
See the shared [paper delivery contract](../../references/paper-delivery.md).

## Cross-machine sync (setup note)

Keep paper PDFs as **imported files** (stored inside Zotero, `linkMode 0`). Zotero's
File Syncing (Zotero Storage or WebDAV, e.g. Nutstore's WebDAV endpoint) then carries
them to every machine automatically — this is what the rest of your library already
relies on.

Do **not** use a mover plugin like **ZotMoov** that converts attachments into *linked
files* pointing at an external folder. Zotero File Syncing does not sync linked files,
so their PDFs never reach your other machines; worse, if the mover's target folder isn't
inside Zotero's Linked Attachment Base Directory, the link is stored as an absolute path
(`/Users/…`) that locks the file to one machine. If you want an external, human-browsable
folder structure instead, you must sync that folder yourself (Nutstore desktop client /
Dropbox) and set each machine's base directory to it — a separate, more fragile setup.
The simple path is: leave attachments imported, let Zotero sync them.

See [SKILL.md](./SKILL.md) for the full procedure and constraints.
