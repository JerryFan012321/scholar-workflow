# Concurrent paper owner creation: independent expectations

Prepared before the test implementation and not yet executed. This is an offline,
single-object concurrency contract, not a real Zotero/Vault action or load test.

## Fixed input

- Two sibling pytest Source directories, each containing only an existing
  `README.md`, are explicitly initialized through `register_source` using one
  synthetic host registry. Both resulting bound providers have zero paper owners.
- Both callers use library `123`, item `ABCD2345`, attachment `EFGH2345`, and the
  same synthetic local PDF bytes. Metadata and the local locator come from an
  in-memory fake Local API. No network or shell command is used.
- Each Source independently obtains its own valid, zero-write `paper_plan` before
  either registration begins. Both plans observe both providers empty.
- Two separate multiprocessing workers receive explicit registry/PDF paths,
  their own immutable selection and approved digest. The parent holds no product
  locks when creating the workers.
- Both workers signal ready and wait on the same bounded start event. Only after
  both are ready does the parent release registration simultaneously. This uses
  actual OS processes, not threads or a mocked scheduler/lock.

## Hand-written expected outcome

1. Exactly one worker returns `registered`; exactly one catches and returns
   `FieldRegistryError`. Any other exception, silent exit, timeout or extra success
   fails the test. Either Source may win; scheduling order is not prescribed.
2. Across both provider JSON declarations there is exactly one atomic resource
   with `resource_id = paper:zotero:123:ABCD2345`, and exactly one matching catalog
   resource. Both declarations belong to the winning Source; the losing provider
   remains byte-identical to its initial empty snapshot.
3. Exactly one `resources/papers/concurrent-paper/Paper.md` and exactly one matching
   Field navigation item exist. Both belong to the winner. The loser's manifest
   stays byte-identical to its pre-race manifest; it receives no paper folder.
4. Both original README byte strings and the shared host registry bytes remain
   unchanged. The fake PDF remains unchanged. No original body is rewritten.
5. Both workers finish with exit code zero, because refusal is explicitly reported
   to the parent. No child is alive when the test completes. A bounded deadline,
   `finally` cleanup, terminate/join and last-resort kill/join prevent deadlocks or
   orphaned test children even when the assertions fail.

## Oracle and scope

The parent inspects generated JSON/YAML, exact fixture bytes, process exit codes
and returned statuses directly. Production validators, lock functions, hash
helpers and source-inventory internals are not expected-result oracles. Queue
messages are bounded test observations, not ownership authority. The test does not
create or inspect real Vaults, launch applications, install plugins, publish builds,
download PDFs, run paper code or certify scientific content.
