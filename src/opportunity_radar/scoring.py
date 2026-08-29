"""Transparent, profile-driven scoring.

All weights live in profile.yaml and are printed with every run — no hidden
magic. ``score_item`` returns a full per-component breakdown so a human (or a
judge) can see exactly why an item ranked where it did.

Components:
  vendor_bonus        organizer matches the personal vendor-sponsor list
  theme_match         per matching theme keyword (capped)
  prize_floor_bonus   USD prize at/above the personal floor
  urgency             deadline proximity within the horizon (closer = higher)
  field_size_penalty  very large registration counts reduce expected value
  featured_bonus      platform-featured listing
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import yaml

DEFAULT_PROFILE: dict = {
    "themes": ["ai", "agents", "machine learning", "llm", "automation"],
    "vendors": ["google", "aws", "amazon", "microsoft", "nvidia", "github", "anthropic", "openai"],
    "prize_floor_usd": 25000,
    "weights": {
        "vendor_bonus": 25.0,
        "theme_match": 10.0,
        "theme_match_cap": 30.0,
        "prize_floor_bonus": 20.0,
        "urgency_max": 20.0,
        "field_size_penalty": -15.0,
        "featured_bonus": 5.0,
    },
    "deadline": {"horizon_days": 45},
    "field_size": {"large_threshold": 2000},
}


def load_profile(path: str | Path | None) -> dict:
    """Load a profile YAML, layered over DEFAULT_PROFILE (shallow per-section)."""
    profile = {k: (dict(v) if isinstance(v, dict) else list(v) if isinstance(v, list) else v)
               for k, v in DEFAULT_PROFILE.items()}
    if path is None:
        return profile
    loaded = yaml.safe_load(Path(path).read_text()) or {}
    for key, value in loaded.items():
        if isinstance(value, dict) and isinstance(profile.get(key), dict):
            profile[key].update(value)
        else:
            profile[key] = value
    return profile


def format_weights(profile: dict) -> str:
    """Human-readable weights block, printed with every run (transparency rule)."""
    lines = ["Scoring weights (from profile — no hidden magic):"]
    for name, value in profile["weights"].items():
        lines.append(f"  {name:<22} {value:+g}")
    lines.append(f"  prize_floor_usd        {profile['prize_floor_usd']:,}")
    lines.append(f"  deadline_horizon_days  {profile['deadline']['horizon_days']}")
    lines.append(f"  field_large_threshold  {profile['field_size']['large_threshold']:,}")
    lines.append(f"  themes: {', '.join(profile['themes'])}")
    lines.append(f"  vendors: {', '.join(profile['vendors'])}")
    return "\n".join(lines)


def _vendor_bonus(item: dict, profile: dict) -> float:
    org = (item.get("organization") or "").lower()
    title = (item.get("title") or "").lower()
    for vendor in profile["vendors"]:
        v = vendor.lower()
        if v and (v in org or v in title):
            return float(profile["weights"]["vendor_bonus"])
    return 0.0


def _theme_match(item: dict, profile: dict) -> float:
    haystack = " ".join(
        [item.get("title", "")] + [t for t in item.get("themes", [])]
    ).lower()
    per_match = float(profile["weights"]["theme_match"])
    cap = float(profile["weights"]["theme_match_cap"])
    matches = sum(1 for kw in profile["themes"] if kw.lower() in haystack)
    return min(matches * per_match, cap)


def _prize_floor_bonus(item: dict, profile: dict) -> float:
    prize = item.get("prize_usd")
    if prize is not None and prize >= profile["prize_floor_usd"]:
        return float(profile["weights"]["prize_floor_bonus"])
    return 0.0


def _urgency(item: dict, profile: dict, now: datetime) -> float:
    """Closer (but not past) deadlines score higher, linearly within the horizon."""
    deadline = item.get("deadline")
    if deadline is None:
        return 0.0
    days_left = (deadline - now).total_seconds() / 86400.0
    if days_left < 0:
        return 0.0  # already closed; selection also filters these out
    horizon = float(profile["deadline"]["horizon_days"])
    urgency_max = float(profile["weights"]["urgency_max"])
    return round(urgency_max * max(0.0, 1.0 - days_left / horizon), 2)


def _field_size_penalty(item: dict, profile: dict) -> float:
    count = item.get("registrations_count")
    if count is not None and count >= profile["field_size"]["large_threshold"]:
        return float(profile["weights"]["field_size_penalty"])
    return 0.0


def _featured_bonus(item: dict, profile: dict) -> float:
    if item.get("featured"):
        return float(profile["weights"].get("featured_bonus", 0.0))
    return 0.0


def score_item(item: dict, profile: dict, now: datetime) -> dict:
    """Score one normalized item. Returns {'total': float, 'breakdown': {...}}.

    The breakdown always sums exactly to the total (tested).
    """
    breakdown = {
        "vendor_bonus": _vendor_bonus(item, profile),
        "theme_match": _theme_match(item, profile),
        "prize_floor_bonus": _prize_floor_bonus(item, profile),
        "urgency": _urgency(item, profile, now),
        "field_size_penalty": _field_size_penalty(item, profile),
        "featured_bonus": _featured_bonus(item, profile),
    }
    return {"total": round(sum(breakdown.values()), 2), "breakdown": breakdown}
