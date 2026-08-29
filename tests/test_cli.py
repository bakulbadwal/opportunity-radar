"""CLI end-to-end on fixtures — fully offline, no google imports anywhere."""

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parents[1]


def test_cli_scan_end_to_end(tmp_path, fixture_path):
    out = tmp_path / "brief.md"
    state = tmp_path / "state.json"
    proc = subprocess.run(
        [
            sys.executable, "-m", "opportunity_radar", "scan",
            "--fixtures", str(fixture_path),
            "--state", str(state),
            "--out", str(out),
            "--now", "2026-08-25T12:00:00",
        ],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    assert proc.returncode == 0, proc.stderr
    assert "Scoring weights" in proc.stderr  # transparency: printed every run
    assert "selected=5" in proc.stderr
    brief = out.read_text()
    assert "Opportunity Radar — weekly brief (2026-08-25)" in brief
    assert brief.count("## ") == 5
    assert state.exists()


def test_cli_scan_second_run_dedupes(tmp_path, fixture_path):
    state = tmp_path / "state.json"
    args = [
        sys.executable, "-m", "opportunity_radar", "scan",
        "--fixtures", str(fixture_path),
        "--state", str(state),
        "--now", "2026-08-25T12:00:00",
    ]
    first = subprocess.run(args, capture_output=True, text=True, cwd=REPO_ROOT)
    assert first.returncode == 0, first.stderr
    second = subprocess.run(args, capture_output=True, text=True, cwd=REPO_ROOT)
    assert second.returncode == 0, second.stderr
    assert "new=0" in second.stderr
    assert "Nothing new above the bar" in second.stdout


def test_cli_demo_runs_offline(tmp_path):
    proc = subprocess.run(
        [sys.executable, "-m", "opportunity_radar", "demo"],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    assert proc.returncode == 0, proc.stderr
    assert "Opportunity Radar — weekly brief" in proc.stdout
