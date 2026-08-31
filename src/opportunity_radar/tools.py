"""ADK tool functions (plain Python — ADK wraps them as FunctionTools).

No google imports here: these are ordinary deterministic functions that the
agent layer calls. Docstrings and type hints matter — ADK generates each
tool's schema from the signature and sends the docstring to the LLM.

The tools share a small in-process context so a conversation can go
scan -> dedupe -> score -> brief without re-passing data through the model.
The model never fabricates opportunities: everything flows from these tools.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

from .brief import render_brief
from .radar import run_radar
from .scoring import format_weights, load_profile, score_item
from .sources import DevpostSource, FixtureSource
from .state import LocalJSONState

# In-process context shared across tool calls within one agent session.
_CONTEXT: dict = {"items": [], "selected": []}


def _profile() -> dict:
    return load_profile(os.environ.get("RADAR_PROFILE") or _find_profile())


def _find_profile() -> str | None:
    for candidate in ("profile.yaml", "profile.example.yaml"):
        if Path(candidate).exists():
            return candidate
    return None


def _state():
    """State backend for the agent layer.

    Set RADAR_FIRESTORE=true to give the ADK agent the same Firestore memory
    the CLI's --firestore flag uses, so a run driven from the ADK web UI lands
    in the same place as a run driven from the terminal. Defaults to the local
    JSON file so the agent still works with no cloud and no credentials.
    """
    if os.environ.get("RADAR_FIRESTORE", "").strip().lower() in ("1", "true", "yes"):
        from .state import FirestoreState  # lazy: keeps the [gcp] extra optional

        return FirestoreState()
    return LocalJSONState(os.environ.get("RADAR_STATE", ".radar-state.json"))


def _source():
    fixtures = os.environ.get("RADAR_FIXTURES")
    if fixtures:
        return FixtureSource(fixtures)
    return DevpostSource()


def scan_sources() -> dict:
    """Fetch and normalize all configured opportunity sources.

    Uses the fixture file in RADAR_FIXTURES if set (offline mode), otherwise
    the live Devpost API. Returns a summary and caches the normalized items
    for the other tools.

    Returns:
        dict: {"status", "count", "titles"} — number of opportunities fetched
        and their titles. Full data stays in deterministic storage; call
        get_new_since_last_run and write_brief next.
    """
    items = _source().fetch()
    _CONTEXT["items"] = items
    return {
        "status": "success",
        "count": len(items),
        "titles": [i["title"] for i in items],
    }


def get_new_since_last_run() -> dict:
    """Filter the scanned opportunities down to ones never seen in past runs.

    Dedupes against the persistent state file and drops already-closed items.
    Requires scan_sources to have been called first.

    Returns:
        dict: {"status", "new_count", "skipped_seen", "skipped_closed", "selected"}
        where "selected" is the scored top-5 list (title, url, prize, deadline,
        score breakdown). These are the ONLY items a brief may mention.
    """
    if not _CONTEXT["items"]:
        return {"status": "error", "message": "Call scan_sources first."}
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    result = run_radar(
        sources=[_CachedSource(_CONTEXT["items"])],
        state=_state(),
        profile=_profile(),
        now=now,
        top_n=5,
    )
    _CONTEXT["selected"] = result.selected
    _CONTEXT["now"] = now
    return {
        "status": "success",
        "new_count": len(result.new_items),
        "skipped_seen": result.skipped_seen,
        "skipped_closed": result.skipped_closed,
        "selected": [_public(i) for i in result.selected],
    }


def score_items() -> dict:
    """Show the transparent score breakdown for every scanned opportunity.

    Scores use the weights in profile.yaml (vendor bonus, theme keywords,
    prize floor, deadline urgency, field-size penalty) — no hidden magic.

    Returns:
        dict: {"status", "weights", "scores"} where scores is a list of
        {title, total, breakdown} sorted best-first.
    """
    if not _CONTEXT["items"]:
        return {"status": "error", "message": "Call scan_sources first."}
    profile = _profile()
    now = _CONTEXT.get("now") or datetime.now(timezone.utc).replace(tzinfo=None)
    scored = []
    for item in _CONTEXT["items"]:
        s = score_item(item, profile, now)
        scored.append({"title": item["title"], "total": s["total"], "breakdown": s["breakdown"]})
    scored.sort(key=lambda x: -x["total"])
    return {"status": "success", "weights": format_weights(profile), "scores": scored}


def write_brief() -> dict:
    """Render the deterministic markdown brief from the selected items only.

    Requires get_new_since_last_run to have been called first. The returned
    markdown is ground truth: every URL, prize, and deadline in it comes from
    the selected items. Never add opportunities, URLs, or amounts beyond it.

    Returns:
        dict: {"status", "markdown"}.
    """
    selected = _CONTEXT.get("selected", [])
    now = _CONTEXT.get("now") or datetime.now(timezone.utc).replace(tzinfo=None)
    markdown = render_brief(selected, now, format_weights(_profile()))
    return {"status": "success", "markdown": markdown}


def _public(item: dict) -> dict:
    deadline = item.get("deadline")
    return {
        "title": item["title"],
        "url": item["url"],
        "organization": item.get("organization"),
        "prize_raw": item.get("prize_raw"),
        "prize_usd": item.get("prize_usd"),
        "deadline": deadline.strftime("%Y-%m-%d") if deadline else None,
        "themes": item.get("themes", []),
        "score": item.get("score"),
    }


class _CachedSource:
    """Wraps already-fetched items so run_radar can reuse them."""

    name = "cached"

    def __init__(self, items: list[dict]):
        self._items = items

    def fetch(self) -> list[dict]:
        return self._items
