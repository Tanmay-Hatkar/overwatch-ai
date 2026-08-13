"""
test_extraction_eval.py — pytest wrapper around the eval harness.

Marked `eval` and excluded from the default suite (see pyproject.toml's
addopts) because this makes REAL LLM calls -- it costs API usage and
isn't fully deterministic across provider updates, unlike every other
test in this repo. Run it explicitly:

  pytest -m eval
  # or, for a readable report instead of pytest's terse output:
  python scripts/run_eval.py

Per the Definition of Done, run this whenever backend/app/prompts/{chat,
commitment_parser}.py changes.
"""

import pytest

from tests.eval.runner import require_openai_configured, run_all, summarize

pytestmark = pytest.mark.eval


def test_extraction_accuracy_meets_baseline() -> None:
    """
    Coarse regression gate: with ~20 hand-labeled cases, per-category
    percentages aren't statistically meaningful yet (see the AI-foundation
    plan's success metrics for the target thresholds once the dataset
    grows toward ~40 cases). For now, assert nothing regresses below an
    80% overall pass rate, and print every failing case's detail so a
    real drop is diagnosable from CI output, not just a number.
    """
    require_openai_configured()

    results = run_all()
    summary = summarize(results)

    failures = [r for r in results if not r.passed]
    if failures:
        lines = [f"{r.id} ({r.category}): {r.error or r.checks}" for r in failures]
        print("\nFailing cases:\n" + "\n".join(lines))

    assert summary["pass_rate"] >= 0.80, (
        f"Extraction eval pass rate {summary['pass_rate']:.0%} is below the "
        f"80% baseline gate ({summary['total_passed']}/{summary['total']}). "
        f"By category: {summary['by_category']}"
    )
