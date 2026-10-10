"""Synthetic navigation fixture only; do not execute this file."""
from prepare import prepare


def build_inputs():
    """The literal call below supports a static relationship, not a run claim."""
    return prepare(["fixture-row"])
