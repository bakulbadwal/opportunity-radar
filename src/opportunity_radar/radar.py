"""Orchestration: fetch -> normalize -> dedupe -> score -> select -> persist.

Pure and testable: the clock is injected (``now`` is a parameter — no
wall-clock reads inside the logic), sources and state are interfaces, and the
model is nowhere in this pipeline. Selection is 100% deterministic.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from .scoring import score_item
from .sources import Source
from .state import State


@dataclass
class RadarResult:
    """Everything a run produced, for rendering and inspection."""

    now: datetime
    all_items: list[dict] = field(default_factory=list)      # everything fetched
    new_items: list[dict] = field(default_factory=list)      # not seen before, still open
    selected: list[dict] = field(default_factory=list)       # top N of new, scored
    skipped_seen: int = 0
    skipped_closed: int = 0


def run_radar(
    sources: list[Source],
    state: State,
    profile: dict,
    now: datetime,
    top_n: int = 5,
) -> RadarResult:
    """Run the deterministic pipeline once.

    - fetch all sources (already normalized by the Source implementations)
    - dedupe against persistent state (seen ids survive across runs)
    - drop items whose deadline has already passed at ``now``
    - score every new item against the profile (transparent breakdown attached
      as item['score'])
    - select the top N by score (ties broken by earlier deadline, then id)
    - persist seen ids + last-run timestamp
    """
    result = RadarResult(now=now)

    for source in sources:
        result.all_items.extend(source.fetch())

    seen = state.get_seen_ids()
    for item in result.all_items:
        if item["id"] in seen:
            result.skipped_seen += 1
            continue
        deadline = item.get("deadline")
        if deadline is not None and deadline < now:
            result.skipped_closed += 1
            continue
        item["score"] = score_item(item, profile, now)
        result.new_items.append(item)

    def sort_key(item: dict):
        deadline = item.get("deadline")
        return (
            -item["score"]["total"],
            deadline or datetime.max,
            item["id"],
        )

    result.selected = sorted(result.new_items, key=sort_key)[:top_n]

    # Persist: every fetched id is now "seen", so the next run only surfaces
    # genuinely new opportunities.
    state.add_seen_ids({item["id"] for item in result.all_items})
    state.set_last_run(now.isoformat())
    return result
