"""Compute the deterministic example result without writing an output file."""

import csv
import json
from pathlib import Path

config = json.loads(Path("configs/recipes/sum.json").read_text(encoding="utf-8"))
with Path(config["dataset"]).open(encoding="utf-8", newline="") as stream:
    values = [int(row["value"]) for row in csv.DictReader(stream)]
if config["operations"] != ["count", "sum", "mean"] or not values:
    raise ValueError("unsupported recipe or empty dataset")
print(
    json.dumps(
        {"count": len(values), "sum": sum(values), "mean": sum(values) / len(values)},
        sort_keys=True,
        indent=2,
    )
)
