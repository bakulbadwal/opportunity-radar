"""Prize parsing, deadline parsing, and normalization — all offline."""

from datetime import datetime

from opportunity_radar.sources import (
    FixtureSource,
    normalize_devpost,
    parse_deadline,
    parse_prize,
)


def test_parse_prize_usd_html():
    usd, raw = parse_prize('<span data-currency="USD">$</span>50,000')
    assert usd == 50000.0
    assert raw == "$50,000"


def test_parse_prize_rupee_is_conservative():
    usd, raw = parse_prize('<span data-currency="INR">₹</span>8,00,000')
    assert usd is None  # never guess exchange rates
    assert "₹" in raw


def test_parse_prize_empty():
    assert parse_prize("") == (None, "")
    assert parse_prize(None) == (None, "")


def test_parse_prize_plain_dollars_with_cents():
    usd, raw = parse_prize("$1,234.56 in prizes")
    assert usd == 1234.56
    assert raw == "$1,234.56 in prizes"


def test_parse_prize_no_amount():
    usd, raw = parse_prize("Swag and glory")
    assert usd is None
    assert raw == "Swag and glory"


def test_parse_deadline_range():
    assert parse_deadline("Aug 10 - Sep 05, 2026") == datetime(2026, 9, 5)


def test_parse_deadline_full_range():
    assert parse_deadline("Aug 25, 2026 - Sep 30, 2026") == datetime(2026, 9, 30)


def test_parse_deadline_garbage_returns_none():
    assert parse_deadline("TBD") is None
    assert parse_deadline("") is None


def test_normalize_devpost_fields():
    raw = {
        "id": 42,
        "title": "Test Hack",
        "url": "https://example.com/hack",
        "prize_amount": '<span data-currency="USD">$</span>1,000',
        "submission_period_dates": "Aug 01 - Sep 01, 2026",
        "themes": [{"name": "AI"}, {"name": ""}],
        "registrations_count": 10,
        "organization_name": "Acme",
        "featured": True,
        "displayed_location": {"location": "Online"},
    }
    item = normalize_devpost(raw)
    assert item["id"] == "devpost:42"
    assert item["source"] == "devpost"
    assert item["prize_usd"] == 1000.0
    assert item["deadline"] == datetime(2026, 9, 1)
    assert item["themes"] == ["AI"]  # empty names dropped
    assert item["organization"] == "Acme"
    assert item["featured"] is True
    assert item["location"] == "Online"


def test_fixture_source_loads_all_entries(fixture_path):
    items = FixtureSource(fixture_path).fetch()
    assert len(items) == 10
    assert all(i["id"].startswith("devpost:") for i in items)
    # fixture includes a non-USD prize and a no-prize entry
    assert any(i["prize_usd"] is None and "₹" in i["prize_raw"] for i in items)
    assert any(i["prize_raw"] == "" for i in items)
