#!/usr/bin/env python3
"""Opportunity Radar eval gate.

Runs offline, exit codes are real (0 = all pass, 1 = any failure):

1. GOLDEN SCENARIO — run the full deterministic pipeline on the checked-in
   fixture with a frozen clock and assert the known-good selection, then
   render the brief and require it to pass the anti-invention gate.
2. GATE SELF-TEST (negative controls) — briefs containing an invented URL,
   an invented dollar figure, and an invented deadline must each FAIL the
   gate. A gate that can't catch a planted lie is not a gate.

Usage: python evals/run_evals.py
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from opportunity_radar.brief import render_brief, validate_brief  # noqa: E402
from opportunity_radar.radar import run_radar  # noqa: E402
from opportunity_radar.scoring import format_weights, load_profile  # noqa: E402
from opportunity_radar.sources import FixtureSource  # noqa: E402
from opportunity_radar.state import LocalJSONState  # noqa: E402

FIXTURE = REPO_ROOT / "tests" / "fixtures" / "devpost_sample.json"
PROFILE = REPO_ROOT / "profile.example.yaml"
NOW = datetime(2026, 8, 25, 12, 0, 0)

FAILURES: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    status = "PASS" if ok else "FAIL"
    print(f"[{status}] {name}" + (f" — {detail}" if detail and not ok else ""))
    if not ok:
        FAILURES.append(name)


def main() -> int:
    import tempfile

    profile = load_profile(PROFILE)
    print(format_weights(profile))
    print()

    # ---- 1. Golden scenario -------------------------------------------------
    with tempfile.TemporaryDirectory() as tmp:
        state = LocalJSONState(Path(tmp) / "state.json")
        result = run_radar([FixtureSource(FIXTURE)], state, profile, NOW, top_n=5)

    check("golden: fetched all 10 fixture items", len(result.all_items) == 10,
          f"got {len(result.all_items)}")
    check("golden: closed item filtered", result.skipped_closed == 1,
          f"got {result.skipped_closed}")
    check("golden: 5 selected", len(result.selected) == 5,
          f"got {len(result.selected)}")

    top = result.selected[0]
    check(
        "golden: Google Cloud Agents Blitz ranks #1 (vendor+themes+prize+urgency+featured)",
        top["id"] == "devpost:21001",
        f"got {top['id']} ({top['title']})",
    )
    selected_ids = {i["id"] for i in result.selected}
    check("golden: crowded off-profile mini-hack not selected",
          "devpost:21005" not in selected_ids)

    brief = render_brief(result.selected, NOW, format_weights(profile))
    run_date = {NOW.strftime("%Y-%m-%d")}
    ok, problems = validate_brief(brief, result.selected, extra_allowed_dates=run_date)
    check("golden: deterministic brief passes anti-invention gate", ok, "; ".join(problems))

    # ---- 2. Gate self-test: negative controls -------------------------------
    planted = {
        "invented URL": brief + "\nBonus round at https://fabricated-event.example.net/",
        "invented dollar figure": brief + "\nGrand total: $123,456,789 in prizes!",
        "invented deadline": brief + "\nFinal cutoff is 2027-01-01.",
    }
    for label, bad_brief in planted.items():
        ok, problems = validate_brief(bad_brief, result.selected, extra_allowed_dates=run_date)
        check(f"negative control: gate catches {label}", not ok,
              "gate PASSED a brief containing a planted lie")

    # ---- verdict ------------------------------------------------------------
    print()
    if FAILURES:
        print(f"EVALS FAILED ({len(FAILURES)}): " + ", ".join(FAILURES))
        return 1
    print("ALL EVALS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
