"""Opportunity sources.

A Source yields *normalized* opportunity dicts. All parsing is deterministic
Python — no model involvement. The Devpost response shape handled here was
verified against the live endpoint on 2026-08-24:

    GET https://devpost.com/api/hackathons?order_by=deadline&status[]=open&challenge_type[]=online

    {"hackathons": [{"id": ..., "title": ..., "url": ...,
                     "prize_amount": "<span data-currency=\"USD\">$</span>50,000",
                     "submission_period_dates": "Aug 20 - Sep 05, 2026",
                     "time_left_to_submission": "...", "themes": [{"name": ...}],
                     "registrations_count": ..., "organization_name": ...,
                     "featured": ..., "displayed_location": {"location": ...}}]}

Normalized item schema (plain dict, JSON-serializable except `deadline`):
    id                str   stable id, e.g. "devpost:123456"
    source            str   source name
    title             str
    url               str
    organization      str
    prize_usd         float | None   conservative: USD-denominated prizes only
    prize_raw         str            human-readable prize text (tags stripped)
    deadline          datetime | None (naive, local-agnostic)
    themes            list[str]
    registrations_count int | None
    location          str
    featured          bool
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

from dateutil import parser as dateparser

DEVPOST_API_URL = "https://devpost.com/api/hackathons"

_TAG_RE = re.compile(r"<[^>]+>")
_MONTH_WORD_RE = re.compile(r"[A-Za-z]{3,}")
_USD_AMOUNT_RE = re.compile(r"\$\s*([\d][\d,]*(?:\.\d+)?)")
_NON_USD_CURRENCY_RE = re.compile(r"[₹€£¥]|\b(?:INR|EUR|GBP|JPY|CAD|AUD|NZD|MXN|CHF|SGD|HKD)\b|(?:CAD|NZ|MXN|AU|HK|S)\$|\bC\$", re.IGNORECASE)


def strip_html(text: str) -> str:
    """Remove HTML tags from a string (Devpost embeds currency spans in prizes)."""
    return _TAG_RE.sub("", text or "").strip()


def parse_prize(prize_html: str) -> tuple[float | None, str]:
    """Parse a Devpost prize string into (prize_usd, prize_raw).

    Conservative policy: only clearly USD-denominated amounts produce a
    numeric ``prize_usd``. Non-USD currencies (₹, €, £, ...) keep their raw
    text but return ``None`` — we never guess exchange rates. Empty or
    unparseable input returns (None, raw).
    """
    raw = strip_html(prize_html)
    if not raw:
        return None, ""
    if _NON_USD_CURRENCY_RE.search(raw):
        return None, raw
    m = _USD_AMOUNT_RE.search(raw)
    if not m:
        return None, raw
    try:
        return float(m.group(1).replace(",", "")), raw
    except ValueError:  # pragma: no cover - regex guarantees digits
        return None, raw


def parse_deadline(submission_period_dates: str) -> datetime | None:
    """Parse the *end* of a Devpost submission period, conservatively.

    Handles "Aug 20 - Sep 05, 2026" and "Aug 25, 2026 - Sep 30, 2026".

    Same-month ranges omit the month on the end ("Aug 07 - 31, 2026"), which
    would otherwise leave "31, 2026" — unparseable, so the deadline silently
    vanished and the item lost its urgency score. Carry the month over from the
    start of the range in that case. Still returns None rather than guessing
    when the string genuinely doesn't parse.
    """
    text = (submission_period_dates or "").strip()
    if not text:
        return None
    if " - " in text:
        start_part, end_part = (p.strip() for p in text.rsplit(" - ", 1))
        if not _MONTH_WORD_RE.search(end_part):
            start_month = _MONTH_WORD_RE.search(start_part)
            if start_month:
                end_part = f"{start_month.group(0)} {end_part}"
    else:
        end_part = text
    try:
        return dateparser.parse(end_part, fuzzy=False)
    except (ValueError, OverflowError):
        return None


def normalize_devpost(raw: dict) -> dict:
    """Normalize one raw Devpost hackathon record into the common schema."""
    prize_usd, prize_raw = parse_prize(raw.get("prize_amount", ""))
    themes = [t.get("name", "") for t in raw.get("themes", []) if t.get("name")]
    location = (raw.get("displayed_location") or {}).get("location", "")
    return {
        "id": f"devpost:{raw.get('id')}",
        "source": "devpost",
        "title": raw.get("title", ""),
        "url": raw.get("url", ""),
        "organization": raw.get("organization_name", "") or "",
        "prize_usd": prize_usd,
        "prize_raw": prize_raw,
        "deadline": parse_deadline(raw.get("submission_period_dates", "")),
        "themes": themes,
        "registrations_count": raw.get("registrations_count"),
        "location": location,
        "featured": bool(raw.get("featured", False)),
    }


class Source:
    """Interface: a source of normalized opportunity dicts."""

    name: str = "source"

    def fetch(self) -> list[dict]:  # pragma: no cover - interface
        raise NotImplementedError


class DevpostSource(Source):
    """Live Devpost API source.

    Endpoint and params verified 2026-08-24. Never exercised by tests
    (tests use FixtureSource); network use is opt-in at runtime.
    """

    name = "devpost"

    def __init__(self, order_by: str = "deadline", timeout: int = 30):
        self.order_by = order_by
        self.timeout = timeout

    def fetch(self) -> list[dict]:
        import requests  # local import keeps module importable without network intent

        resp = requests.get(
            DEVPOST_API_URL,
            params={
                "order_by": self.order_by,
                "status[]": "open",
                "challenge_type[]": "online",
            },
            headers={"User-Agent": "opportunity-radar/0.1 (+hackathon draft)"},
            timeout=self.timeout,
        )
        resp.raise_for_status()
        payload = resp.json()
        return [normalize_devpost(h) for h in payload.get("hackathons", [])]


class FixtureSource(Source):
    """Reads a saved Devpost-shaped JSON payload from disk. Used by all tests."""

    name = "devpost-fixture"

    def __init__(self, path: str | Path):
        self.path = Path(path)

    def fetch(self) -> list[dict]:
        payload = json.loads(self.path.read_text())
        return [normalize_devpost(h) for h in payload.get("hackathons", [])]
