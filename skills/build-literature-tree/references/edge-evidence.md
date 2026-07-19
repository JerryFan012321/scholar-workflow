# Edge Evidence

## Relation types

| Type | Meaning | Citation alone enough? |
|---|---|---|
| `cites` | A cites B | Yes |
| `follow-up` | A continues B's line of work | No — needs body evidence |
| `method-extension` | A extends B's method | No — needs body evidence |
| `representation-shift` | A changes B's representation | No — needs body evidence |
| `benchmark-successor` | A supersedes B as benchmark | No — citations + body |
| `contradicts` | A refutes / conflicts with B | No — explicit body statement |

## Evidence requirements

- `cites`: no extra evidence; the citation is the evidence.
- All others: at least one `paper-text` or `abstract` evidence item, each with
  source type, text location (introduction / method / abstract), and a summary.

## Confidence

| Range | Meaning |
|---|---|
| 0.9–1.0 | explicit statement in the paper body |
| 0.6–0.9 | indirect statement in abstract / intro |
| 0.3–0.6 | inferred from context — needs review |
| < 0.3 | do not record; keep as `proposed` |

## Milestones

Never flag a milestone from citation count alone. Requires a high-confidence method
edge plus body evidence from multiple later papers, and user confirmation
(`review_status: confirmed`).
