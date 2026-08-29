"""Brief rendering + the anti-invention gate (self-test with negative controls)."""

from datetime import datetime

from opportunity_radar.brief import render_brief, validate_brief
from opportunity_radar.radar import run_radar
from opportunity_radar.sources import FixtureSource
from opportunity_radar.state import LocalJSONState


def _selected(fixture_path, profile, now, tmp_path):
    state = LocalJSONState(tmp_path / "state.json")
    return run_radar([FixtureSource(fixture_path)], state, profile, now, top_n=5).selected


def test_deterministic_brief_renders_and_passes_gate(fixture_path, profile, now, tmp_path):
    selected = _selected(fixture_path, profile, now, tmp_path)
    brief = render_brief(selected, now)
    assert "Opportunity Radar" in brief
    for item in selected:
        assert item["title"] in brief
        assert item["url"] in brief
    ok, problems = validate_brief(
        brief, selected, extra_allowed_dates={now.strftime("%Y-%m-%d")}
    )
    assert ok, problems


def test_empty_selection_renders(now):
    brief = render_brief([], now)
    assert "0 opportunities" in brief
    assert "keeps watching" in brief


def test_gate_rejects_invented_url(fixture_path, profile, now, tmp_path):
    selected = _selected(fixture_path, profile, now, tmp_path)
    brief = render_brief(selected, now) + "\nAlso check https://totally-invented.example.org/win"
    ok, problems = validate_brief(
        brief, selected, extra_allowed_dates={now.strftime("%Y-%m-%d")}
    )
    assert not ok
    assert any("invented URL" in p for p in problems)


def test_gate_rejects_invented_dollar_figure(fixture_path, profile, now, tmp_path):
    selected = _selected(fixture_path, profile, now, tmp_path)
    brief = render_brief(selected, now) + "\nThe total prize pool is $9,999,999!"
    ok, problems = validate_brief(
        brief, selected, extra_allowed_dates={now.strftime("%Y-%m-%d")}
    )
    assert not ok
    assert any("invented dollar" in p for p in problems)


def test_gate_rejects_invented_deadline(fixture_path, profile, now, tmp_path):
    selected = _selected(fixture_path, profile, now, tmp_path)
    brief = render_brief(selected, now) + "\nHurry, everything closes 2026-12-31."
    ok, problems = validate_brief(
        brief, selected, extra_allowed_dates={now.strftime("%Y-%m-%d")}
    )
    assert not ok
    assert any("invented date" in p for p in problems)


def test_gate_allows_run_date_via_extra_allowed(now):
    brief = f"# Brief ({now.strftime('%Y-%m-%d')})\nNothing new."
    ok, problems = validate_brief(brief, [], extra_allowed_dates={now.strftime("%Y-%m-%d")})
    assert ok, problems
    # ...and without the exemption the same date is flagged
    ok, _ = validate_brief(brief, [])
    assert not ok


def test_gate_amount_matching_is_exact_not_substring():
    items = [
        {
            "url": "https://a.example.com/x",
            "prize_usd": 50000.0,
            "prize_raw": "$50,000",
            "deadline": datetime(2026, 9, 5),
        }
    ]
    ok, _ = validate_brief("Win $50,000 at https://a.example.com/x by 2026-09-05.", items)
    assert ok
    ok, problems = validate_brief("Win $5,000!", items)
    assert not ok
