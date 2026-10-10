# review-experiments

Review existing project experiments without rerunning them or building another
dashboard. Select the project, Runs, result Attempts and metrics; the skill returns
an evidence-linked Markdown report. Ambiguous selections are clarified, not replaced
with the highest-scoring or latest result.

Example request:

> Compare the selected baseline and variant Runs using each primary Attempt's
> accuracy artifact. Include their Attempt histories and explain missing evidence.
> Return Markdown; do not run code or change the project.

The report leads with a plain-language conclusion, a supported figure and selected
results; unavailable visual evidence is stated rather than invented. It separates
Run results from retries, lists comparison conditions and
configuration differences, preserves failures, and links to the actual records and
artifacts. Missing units/protocols do not silently inherit another Run's metadata.
Remote-only results remain unavailable without a separate acquisition request.
No common metric JSON schema or significance claim is invented.

See [the report contract](../../references/experiment-review.md). Available from
0.43.0; native reading and human usefulness assessment remain separate from installation.
