# Independent paper-owner expectations

Authored before the production change. Synthetic Sources A and B share one explicit
registry; only A initially owns `paper:zotero:123:ABCD2345`. B requests a fresh folder.
The fake Local API has no network access or secrets. All writes stay in pytest roots.

1. The same library ID and item key in A must refuse B's plan as an existing owner.
2. A matching item key with an opaque legacy resource ID cannot prove the library:
   refuse with unverifiable ownership, not a guessed duplicate or an allowed new owner.
3. A canonical resource ID contradicting its item-key declaration is unverifiable.
4. Equal item keys in proven different libraries 123 and 456 are not duplicates;
   planning remains zero-write and allocates `paper:zotero:456:ABCD2345`.
5. Missing, invalid, symlinked, or FIFO provider declarations, a disabled A, or an
   unavailable A root cannot prove global uniqueness; refuse without B content writes.
6. Any A declaration revision after B's preview invalidates B's approved digest,
   including a title-only change unrelated to the requested paper identity.
7. Recovery rechecks the same outside-source read set. A changed A cannot be ignored
   because B already has a prepared journal; preserve B's partial files and journal.
8. Recheck before publishing each next member. An A change after B's first note
   stops before B's navigation/provider publication; retain the recoverable journal.
9. A single Source may contain equal item keys from proven different libraries;
   the existing local key-only duplicate check must not reject library 456 after 123.
10. Unchanged outside declarations permit exact interrupted recovery, producing
    `paper:zotero:456:ABCD2345` at `resources/papers/new-owner/Paper.md`.
11. A human edit to B's partial note refuses recovery and remains byte-for-byte
    unchanged. Global uniqueness checks must not weaken the existing CAS protection.
12. A canonical paper ID declared with a non-paper kind is contradictory, not a
    free identity. Refuse a second owner before any publication.
13. A leading-zero Zotero library ID is not a new library. Refuse the noncanonical
    API identity rather than creating `paper:zotero:0123:ABCD2345`.
14. A completed request can replay unchanged, but must refuse after an outside
    declaration changes or the target Source gains another ambiguous matching owner.
    The latter fixture retains the original receipt and a valid follow-up chain.
15. Same-byte file replacement, Field revision, root/provider directory replacement,
    and registry-set changes invalidate the earlier approval, not only content changes.
16. Cooperative provider locks use sorted Source IDs, exactly once per Source, after
    the registry lock. Never acquire the target first and then reacquire it.

Provider setup uses existing registration only to construct the test state, not to
derive these expected outcomes. No scientific facts, actual paper analyses, external
readers, product installs, source discovery, or permanent data mutations occur.
This suite does not define missing-provider-as-empty semantics or certify safe
concurrent publication; those must be addressed before claiming a complete fix.
