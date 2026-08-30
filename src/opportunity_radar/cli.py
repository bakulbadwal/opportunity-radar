"""CLI: the offline end-to-end path.

    python -m opportunity_radar scan --fixtures tests/fixtures/devpost_sample.json --out brief.md
    python -m opportunity_radar demo
    radar scan ... / radar demo   (console script)

`scan` without --fixtures uses the live Devpost API (network!). Tests only
ever exercise the fixtures path.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

from .brief import gemini_brief, render_brief
from .radar import run_radar
from .scoring import format_weights, load_profile
from .sources import DevpostSource, FixtureSource
from .state import LocalJSONState


def _find_default_profile() -> Path | None:
    for name in ("profile.yaml", "profile.example.yaml"):
        p = Path(name)
        if p.exists():
            return p
    # dev checkout: resolve relative to the repo root
    repo_root = Path(__file__).resolve().parents[2]
    p = repo_root / "profile.example.yaml"
    return p if p.exists() else None


def _demo_fixture() -> Path | None:
    repo_root = Path(__file__).resolve().parents[2]
    p = repo_root / "tests" / "fixtures" / "devpost_sample.json"
    return p if p.exists() else None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="radar",
        description="Opportunity Radar — watches opportunity sources so you don't have to.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    scan = sub.add_parser("scan", help="Run the radar pipeline once.")
    scan.add_argument("--fixtures", help="Path to a Devpost-shaped JSON fixture (offline mode).")
    scan.add_argument("--profile", help="Path to profile YAML (default: profile.yaml or profile.example.yaml).")
    scan.add_argument("--state", default=".radar-state.json", help="State file for dedupe across runs.")
    scan.add_argument("--out", help="Write the brief to this file (default: stdout).")
    scan.add_argument("--top", type=int, default=5, help="How many opportunities to select.")
    scan.add_argument("--now", help="Injected clock, ISO format (default: current UTC). Used by tests/evals.")
    scan.add_argument(
        "--gemini",
        action="store_true",
        help="DRAFT: narrate the brief with Gemini (needs [agent] extra + API key); "
        "output must pass the anti-invention gate or the deterministic brief is used.",
    )
    scan.add_argument(
        "--firestore",
        action="store_true",
        help="DRAFT/UNTESTED: use FirestoreState instead of the local JSON state "
        'file (needs the [gcp] extra + GCP credentials). Meant for Cloud Run Jobs.',
    )

    sub.add_parser("demo", help="Offline demo: run scan on the bundled fixture, fresh state, print brief.")
    return parser


def cmd_scan(args: argparse.Namespace) -> int:
    if args.fixtures:
        source = FixtureSource(args.fixtures)
    else:
        print("[radar] no --fixtures given: hitting the live Devpost API", file=sys.stderr)
        source = DevpostSource()

    profile_path = Path(args.profile) if args.profile else _find_default_profile()
    profile = load_profile(profile_path)
    now = datetime.fromisoformat(args.now) if args.now else datetime.now(timezone.utc).replace(tzinfo=None)
    if getattr(args, "firestore", False):
        from .state import FirestoreState  # DRAFT: raises a clear error without [gcp]

        state = FirestoreState()
    else:
        state = LocalJSONState(args.state)

    result = run_radar([source], state, profile, now, top_n=args.top)

    weights_block = format_weights(profile)
    print(weights_block, file=sys.stderr)  # transparency: weights print every run
    print(
        f"[radar] fetched={len(result.all_items)} new={len(result.new_items)} "
        f"seen={result.skipped_seen} closed={result.skipped_closed} "
        f"selected={len(result.selected)}",
        file=sys.stderr,
    )

    if args.gemini:
        brief = gemini_brief(result.selected, now, weights_block)
    else:
        brief = render_brief(result.selected, now, weights_block)

    if args.out:
        Path(args.out).write_text(brief)
        print(f"[radar] brief written to {args.out}", file=sys.stderr)
    else:
        print(brief)
    return 0


def cmd_demo() -> int:
    fixture = _demo_fixture()
    if fixture is None:
        print(
            "[radar] demo fixture not found — run from a repo checkout "
            "(tests/fixtures/devpost_sample.json).",
            file=sys.stderr,
        )
        return 1
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        args = build_parser().parse_args(
            [
                "scan",
                "--fixtures", str(fixture),
                "--state", str(Path(tmp) / "state.json"),
                "--now", "2026-08-25T12:00:00",
            ]
        )
        return cmd_scan(args)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "demo":
        return cmd_demo()
    return cmd_scan(args)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
