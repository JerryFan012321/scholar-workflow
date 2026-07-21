# ingest-resource

Import papers and archive technical documents into the local library via zotero-mcp.
A paper needs two things: its PDF (from arXiv) and its metadata (from an authoritative
web source, never parsed from the PDF). Three phases:

- **Existence check (read-only)** — normalize the identifier (DOI / title+authors;
  arXiv id is a download-source label, not an identity), then run a two-step check via
  zotero-mcp: `search_library` recall → `get_item_details` confirm. Outcome is
  exact / conflict / none. `write_item` is pure create with no dedup, so this check
  must precede every create.
- **Acquire metadata (read-only web fetch)** — for new items, read metadata from arXiv
  abs / CVF / DBLP / publisher. When a published version exists, its venue overrides the
  arXiv "preprint" label. Don't fabricate missing secondary fields.
- **Write (via zotero-mcp)** — ask which collection the paper belongs to, download the
  arXiv PDF into `paper_inbox`, then `write_item` create + import to attach it, and
  `add_items_to_collection`. Additive writes proceed under the user's standing
  instruction; only delete/overwrite/merge need approval. Technical documents are copied
  into the Vault with source/hash metadata.

Downloaded PDFs go only to `paper_inbox`; technical documents only to the Vault. All
Zotero access is via zotero-mcp — the plugin never writes `zotero.sqlite` directly.

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
