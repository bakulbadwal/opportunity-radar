"""Scoring: transparent breakdowns, vendor/prize/urgency/field-size behavior."""

from datetime import datetime, timedelta

from opportunity_radar.scoring import format_weights, load_profile, score_item


def _item(**overrides) -> dict:
    base = {
        "id": "devpost:1",
        "source": "devpost",
        "title": "Plain Hack",
        "url": "https://example.com",
        "organization": "Nobody Inc",
        "prize_usd": None,
        "prize_raw": "",
        "deadline": None,
        "themes": [],
        "registrations_count": 100,
        "location": "Online",
        "featured": False,
    }
    base.update(overrides)
    return base


def test_breakdown_sums_to_total(items, profile, now):
    for item in items:
        s = score_item(item, profile, now)
        assert abs(sum(s["breakdown"].values()) - s["total"]) < 1e-6


def test_vendor_bonus_applies(profile, now):
    scored = score_item(_item(organization="Google Cloud"), profile, now)
    assert scored["breakdown"]["vendor_bonus"] == profile["weights"]["vendor_bonus"]
    scored = score_item(_item(organization="Nobody Inc"), profile, now)
    assert scored["breakdown"]["vendor_bonus"] == 0.0


def test_theme_match_capped(profile, now):
    item = _item(
        title="AI agents automation llm machine learning productivity",
        themes=["AI", "Agents"],
    )
    scored = score_item(item, profile, now)
    assert scored["breakdown"]["theme_match"] == profile["weights"]["theme_match_cap"]


def test_prize_floor_bonus(profile, now):
    above = score_item(_item(prize_usd=30000.0), profile, now)
    below = score_item(_item(prize_usd=5000.0), profile, now)
    none = score_item(_item(prize_usd=None), profile, now)
    assert above["breakdown"]["prize_floor_bonus"] == profile["weights"]["prize_floor_bonus"]
    assert below["breakdown"]["prize_floor_bonus"] == 0.0
    assert none["breakdown"]["prize_floor_bonus"] == 0.0


def test_deadline_urgency_ordering(profile, now):
    """Closer deadlines must score strictly higher urgency, and past/none score 0."""
    soon = score_item(_item(deadline=now + timedelta(days=3)), profile, now)
    later = score_item(_item(deadline=now + timedelta(days=20)), profile, now)
    distant = score_item(_item(deadline=now + timedelta(days=100)), profile, now)
    past = score_item(_item(deadline=now - timedelta(days=1)), profile, now)
    none = score_item(_item(deadline=None), profile, now)

    assert soon["breakdown"]["urgency"] > later["breakdown"]["urgency"]
    assert later["breakdown"]["urgency"] > distant["breakdown"]["urgency"]
    assert distant["breakdown"]["urgency"] == 0.0  # beyond horizon
    assert past["breakdown"]["urgency"] == 0.0
    assert none["breakdown"]["urgency"] == 0.0


def test_field_size_penalty(profile, now):
    crowded = score_item(_item(registrations_count=5000), profile, now)
    small = score_item(_item(registrations_count=50), profile, now)
    unknown = score_item(_item(registrations_count=None), profile, now)
    assert crowded["breakdown"]["field_size_penalty"] == profile["weights"]["field_size_penalty"]
    assert small["breakdown"]["field_size_penalty"] == 0.0
    assert unknown["breakdown"]["field_size_penalty"] == 0.0


def test_weights_block_prints_every_knob(profile):
    block = format_weights(profile)
    for knob in profile["weights"]:
        assert knob in block
    assert "prize_floor_usd" in block
    assert "themes:" in block


def test_profile_yaml_overrides_defaults(tmp_path):
    p = tmp_path / "profile.yaml"
    p.write_text("prize_floor_usd: 1\nweights:\n  vendor_bonus: 99.0\n")
    profile = load_profile(p)
    assert profile["prize_floor_usd"] == 1
    assert profile["weights"]["vendor_bonus"] == 99.0
    # untouched sections keep defaults
    assert profile["weights"]["urgency_max"] == 20.0
    assert profile["deadline"]["horizon_days"] == 45
