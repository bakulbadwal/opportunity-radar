"""Pipeline: dedupe across runs, closed-item filtering, deterministic selection."""

from opportunity_radar.radar import run_radar
from opportunity_radar.sources import FixtureSource
from opportunity_radar.state import LocalJSONState


def test_first_run_selects_top_n(fixture_path, profile, now, tmp_path):
    state = LocalJSONState(tmp_path / "state.json")
    result = run_radar([FixtureSource(fixture_path)], state, profile, now, top_n=5)
    assert len(result.all_items) == 10
    assert result.skipped_closed == 1  # RetroCode Summer Jam ended Aug 20
    assert len(result.new_items) == 9
    assert len(result.selected) == 5
    # every selected item carries a transparent score breakdown
    for item in result.selected:
        assert "score" in item and "breakdown" in item["score"]
    # sorted best-first
    totals = [i["score"]["total"] for i in result.selected]
    assert totals == sorted(totals, reverse=True)


def test_dedupe_across_runs(fixture_path, profile, now, tmp_path):
    state_path = tmp_path / "state.json"
    src = [FixtureSource(fixture_path)]

    first = run_radar(src, LocalJSONState(state_path), profile, now, top_n=5)
    assert len(first.new_items) == 9

    # Second run with fresh State object over the same file: everything seen.
    second = run_radar(src, LocalJSONState(state_path), profile, now, top_n=5)
    assert second.skipped_seen == 10
    assert second.new_items == []
    assert second.selected == []


def test_state_records_last_run(fixture_path, profile, now, tmp_path):
    state = LocalJSONState(tmp_path / "state.json")
    run_radar([FixtureSource(fixture_path)], state, profile, now)
    assert state.get_last_run() == now.isoformat()


def test_google_agents_hackathon_outranks_web3_minihack(fixture_path, profile, now, tmp_path):
    """Sanity: vendor + themes + prize + featured beats a small off-profile hack."""
    state = LocalJSONState(tmp_path / "state.json")
    result = run_radar([FixtureSource(fixture_path)], state, profile, now, top_n=9)
    ranked_ids = [i["id"] for i in result.selected]
    assert ranked_ids.index("devpost:21001") < ranked_ids.index("devpost:21005")
