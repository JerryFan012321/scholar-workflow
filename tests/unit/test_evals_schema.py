"""Schema-validation tests for evals/*.json.

These files are largely LLM-behavior specs (skill routing, refusal behavior) that
pytest cannot assert as code. This test guards their *structure* instead: valid JSON,
required keys present, ids unique, and enum-like fields within the allowed set — so a
malformed eval file fails CI before it silently rots.
"""
from __future__ import annotations
import json
from pathlib import Path

import pytest

_EVALS = Path(__file__).resolve().parents[2] / "evals"

# Exit codes defined in AGENT.md ("CLI 退出码"). Any exit_code in safety.json must be one.
# 4 is retired (approval gate removed; no CLI trigger path) and must not be reused.
_EXIT_CODES = {0, 2, 3, 5, 6, 7, 8}
_OUTCOME_STATUS = {"pending", "pass", "fail"}
# Where a safety invariant is enforced. Only a 'cli' case can carry a CLI exit_code;
# 'hook' uses the hook protocol and 'host_llm' is skill-layer behavior with no CLI code
# to assert (guarding against the old bug of faking CLI exit codes on host-layer cases).
_ENFORCEMENT_LAYERS = {"hook", "cli", "host_llm"}


def _load(name):
    return json.loads((_EVALS / name).read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def routing():
    return _load("routing.json")


@pytest.fixture(scope="module")
def outcomes():
    return _load("outcomes.json")


@pytest.fixture(scope="module")
def safety():
    return _load("safety.json")


# ---- shared top-level shape ----

@pytest.mark.parametrize("name", ["routing.json", "outcomes.json", "safety.json"])
def test_top_level_shape(name):
    doc = _load(name)
    assert isinstance(doc.get("description"), str) and doc["description"]
    assert isinstance(doc.get("cases"), list) and doc["cases"]


@pytest.mark.parametrize("name", ["routing.json", "outcomes.json", "safety.json"])
def test_case_ids_unique_and_nonempty(name):
    ids = [c.get("id") for c in _load(name)["cases"]]
    assert all(isinstance(i, str) and i for i in ids), f"empty/non-str id in {name}"
    assert len(ids) == len(set(ids)), f"duplicate id in {name}: {ids}"


# ---- routing.json ----

def test_routing_required_fields(routing):
    for c in routing["cases"]:
        assert "input" in c and isinstance(c["input"], str)
        # expected_skill is required and may be null (the no-trigger case)
        assert "expected_skill" in c
        if c["expected_skill"] is not None:
            assert isinstance(c["expected_skill"], str) and c["expected_skill"]


def test_routing_skills_are_real(routing):
    skills_dir = Path(__file__).resolve().parents[2] / "skills"
    known = {p.name for p in skills_dir.iterdir() if (p / "SKILL.md").exists()}
    for c in routing["cases"]:
        if c["expected_skill"] is not None:
            assert c["expected_skill"] in known, f"unknown skill: {c['expected_skill']}"


# ---- outcomes.json ----

def test_outcomes_required_fields(outcomes):
    for c in outcomes["cases"]:
        assert isinstance(c.get("description"), str) and c["description"]
        assert c.get("status") in _OUTCOME_STATUS, f"bad status in {c['id']}"


# ---- safety.json ----

def test_safety_required_fields(safety):
    for c in safety["cases"]:
        assert isinstance(c.get("action"), str) and c["action"]
        assert isinstance(c.get("expected"), str) and c["expected"]
        assert c.get("enforcement_layer") in _ENFORCEMENT_LAYERS, \
            f"bad/missing enforcement_layer in {c['id']}"
        # exit_code is optional and only meaningful for CLI-reachable cases; hook and
        # host_llm cases must not carry one (that was the old false-CLI-code bug).
        if "exit_code" in c:
            assert c["enforcement_layer"] == "cli", \
                f"exit_code on non-cli case {c['id']}"
            assert c["exit_code"] in _EXIT_CODES, f"bad exit_code in {c['id']}"
