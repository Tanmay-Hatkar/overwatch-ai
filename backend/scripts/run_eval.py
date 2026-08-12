"""
run_eval.py — Run the LLM extraction eval harness and print a report.

This makes REAL LLM calls (no mocking) against whichever provider(s) are
configured in backend/.env, same as the running backend. It costs real
API usage — don't wire it into every test run; that's why it lives
outside the default pytest suite (see tests/eval/test_extraction_eval.py
for the pytest.mark.eval wrapper, which is excluded by default).

Run this:
  - manually, per the Definition of Done, whenever
    backend/app/prompts/{chat,commitment_parser}.py changes
  - to get a baseline scorecard before/after any prompt change

Run (from backend/, with the same .env the app uses):
  python scripts/run_eval.py
"""

import sys
from pathlib import Path

# tests/ isn't part of the installed `app` package, so it isn't importable
# by default when this script is run directly (only pytest adds it to
# sys.path automatically, via its rootdir insertion). Add backend/ (this
# script's parent) explicitly.
sys.path.insert(0, str(Path(__file__).parent.parent))

from tests.eval.runner import require_openai_configured, run_all, summarize  # noqa: E402


def main() -> int:
    require_openai_configured()

    results = run_all()
    summary = summarize(results)

    print(f"\n{'=' * 70}\nOverwatch LLM extraction eval\n{'=' * 70}\n")

    for r in results:
        status = "PASS" if r.passed else "FAIL"
        print(f"[{status}] {r.category:24s} {r.id}")
        if r.error:
            print(f"       ERROR: {r.error}")
        for check in r.checks:
            if check.startswith("FAIL"):
                print(f"       {check}")

    print(f"\n{'-' * 70}\nBy category:\n{'-' * 70}")
    for cat, stats in sorted(summary["by_category"].items()):
        print(f"  {cat:28s} {stats['passed']}/{stats['total']}")

    print(f"\n{'-' * 70}")
    print(f"TOTAL: {summary['total_passed']}/{summary['total']} "
          f"({summary['pass_rate']:.0%})")
    print(f"{'-' * 70}\n")

    return 0 if summary["pass_rate"] == 1.0 else 1


if __name__ == "__main__":
    sys.exit(main())
