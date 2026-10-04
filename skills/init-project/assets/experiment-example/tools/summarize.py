"""Thin entrypoint for the example's source module."""

import runpy
from pathlib import Path

runpy.run_path(
    str(Path(__file__).resolve().parents[1] / "src/example_computation.py"), run_name="__main__"
)
