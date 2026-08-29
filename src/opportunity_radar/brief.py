"""Brief rendering: deterministic fallback + gated Gemini narrative.

Architecture rule: the model ONLY writes narrative from already-selected
items. Every URL, dollar figure, and ISO date in a generated brief must exist
in the selected-items input (the anti-invention gate below). If the gate
fails, we fall back to the deterministic renderer and say so in the output.
"""

from __future__ import annotations

import json
import re
from datetime import datetime

_URL_RE = re.compile(r"https?://[^\s)\]>\"',]+")
_DOLLAR_RE = re.compile(r"\$\s*([\d][\d,]*(?:\.\d+)?)")
_ISO_DATE_RE = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")

GEMINI_MODEL = "gemini-3.5-flash"  # primary example model in the google-genai README


# ---------------------------------------------------------------------------
# Anti-invention gate
# ---------------------------------------------------------------------------

def _allowed_facts(items: list[dict], extra_allowed_dates: set[str] | None = None):
    urls: set[str] = set()
    amounts: set[float] = set()
    dates: set[str] = set(extra_allowed_dates or set())
    for item in items:
        if item.get("url"):
            urls.add(item["url"].rstrip("/"))
        if item.get("prize_usd") is not None:
            amounts.add(float(item["prize_usd"]))
        for m in _DOLLAR_RE.finditer(item.get("prize_raw") or ""):
            amounts.add(float(m.group(1).replace(",", "")))
        deadline = item.get("deadline")
        if deadline is not None:
            dates.add(deadline.strftime("%Y-%m-%d"))
    return urls, amounts, dates


def validate_brief(
    brief_text: str,
    items: list[dict],
    extra_allowed_dates: set[str] | None = None,
) -> tuple[bool, list[str]]:
    """Assert every URL, dollar figure, and ISO date in the brief exists in
    the selected-items input. Returns (ok, list_of_problems)."""
    allowed_urls, allowed_amounts, allowed_dates = _allowed_facts(
        items, extra_allowed_dates
    )
    problems: list[str] = []

    for url in _URL_RE.findall(brief_text):
        cleaned = url.rstrip(".,;:!?").rstrip("/")
        if cleaned not in allowed_urls:
            problems.append(f"invented URL: {url}")

    for m in _DOLLAR_RE.finditer(brief_text):
        amount = float(m.group(1).replace(",", ""))
        if amount not in allowed_amounts:
            problems.append(f"invented dollar figure: ${m.group(1)}")

    for m in _ISO_DATE_RE.finditer(brief_text):
        if m.group(1) not in allowed_dates:
            problems.append(f"invented date: {m.group(1)}")

    return (len(problems) == 0), problems


# ---------------------------------------------------------------------------
# Deterministic renderer (always works, no model, no network)
# ---------------------------------------------------------------------------

def render_brief(selected: list[dict], now: datetime, weights_block: str = "") -> str:
    """Deterministic markdown brief from the selected items only."""
    lines = [
        f"# Opportunity Radar — weekly brief ({now.strftime('%Y-%m-%d')})",
        "",
        f"{len(selected)} opportunities selected this run.",
        "",
    ]
    if not selected:
        lines.append("_Nothing new above the bar this week. The radar keeps watching._")
    for i, item in enumerate(selected, 1):
        deadline = item.get("deadline")
        deadline_str = deadline.strftime("%Y-%m-%d") if deadline else "no deadline listed"
        prize = item.get("prize_raw") or "no prize listed"
        lines.append(f"## {i}. {item['title']}")
        lines.append("")
        lines.append(f"- **URL:** {item['url']}")
        lines.append(f"- **Organizer:** {item.get('organization') or 'n/a'}")
        lines.append(f"- **Prize:** {prize}")
        lines.append(f"- **Deadline:** {deadline_str}")
        if item.get("themes"):
            lines.append(f"- **Themes:** {', '.join(item['themes'])}")
        score = item.get("score")
        if score:
            parts = ", ".join(
                f"{k}={v:+g}" for k, v in score["breakdown"].items() if v
            )
            lines.append(f"- **Score:** {score['total']:g}  ({parts or 'no signals'})")
        lines.append("")
    if weights_block:
        lines.append("---")
        lines.append("```")
        lines.append(weights_block)
        lines.append("```")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Gemini narrative (guarded — only runs with a key; output must pass the gate)
# ---------------------------------------------------------------------------

_GEMINI_PROMPT = """You are the writer for Opportunity Radar's weekly brief.

You will receive a JSON array of ALREADY-SELECTED opportunities. Write a short,
energetic markdown brief (under 400 words) summarizing them for a busy person.

Hard rules — violations are automatically rejected by a validation gate:
- Use ONLY the opportunities in the JSON. Do not add, merge, or invent any.
- Every URL, dollar amount, and date you mention must appear verbatim in the JSON.
- Write deadlines in YYYY-MM-DD format exactly as given.
- Do not estimate, convert currencies, or round prize amounts.

Today is {today}. Selected opportunities:

{items_json}
"""


def _items_for_prompt(selected: list[dict]) -> str:
    safe = []
    for item in selected:
        d = {k: v for k, v in item.items() if k != "score"}
        deadline = d.get("deadline")
        d["deadline"] = deadline.strftime("%Y-%m-%d") if deadline else None
        safe.append(d)
    return json.dumps(safe, indent=2)


def gemini_brief(
    selected: list[dict],
    now: datetime,
    weights_block: str = "",
    model: str = GEMINI_MODEL,
) -> str:
    """DRAFT — requires GOOGLE_API_KEY/GEMINI_API_KEY and the [agent] extra.

    Asks Gemini to narrate the already-selected items, then runs the
    anti-invention gate on the output. On any gate failure (or API failure),
    falls back to the deterministic renderer and says so.
    """
    fallback_note = None
    try:
        from google import genai  # guarded: [agent] extra only

        client = genai.Client()  # picks up GEMINI_API_KEY / GOOGLE_API_KEY
        try:
            response = client.models.generate_content(
                model=model,
                contents=_GEMINI_PROMPT.format(
                    today=now.strftime("%Y-%m-%d"),
                    items_json=_items_for_prompt(selected),
                ),
            )
            text = response.text or ""
        finally:
            client.close()

        ok, problems = validate_brief(
            text, selected, extra_allowed_dates={now.strftime("%Y-%m-%d")}
        )
        if ok and text.strip():
            if weights_block:
                text += f"\n\n---\n```\n{weights_block}\n```"
            return text
        fallback_note = (
            "anti-invention gate rejected the model output: "
            + "; ".join(problems or ["empty response"])
        )
    except ImportError:
        fallback_note = 'google-genai not installed (pip install "opportunity-radar[agent]")'
    except Exception as e:  # API/auth errors: never break the pipeline
        fallback_note = f"Gemini call failed: {e.__class__.__name__}: {e}"

    deterministic = render_brief(selected, now, weights_block)
    return (
        f"> NOTE: deterministic fallback used — {fallback_note}\n\n" + deterministic
    )
