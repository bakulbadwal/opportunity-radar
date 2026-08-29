"""DRAFT — ADK agent definition (untested against a live key).

Requires: pip install "opportunity-radar[agent]" and GOOGLE_API_KEY in the
environment (ADK quickstart convention). Never imported by the offline
pipeline or the tests.

Run it with the ADK CLI from the repo root:

    adk run src/opportunity_radar        # terminal chat
    adk web --port 8000                  # dev UI

or programmatically via Runner + InMemorySessionService (see docs/DEPLOY.md).

Import path note: the ADK quickstart uses
``from google.adk.agents.llm_agent import Agent``; the ADK 2.0 README also
ships the shorter ``from google.adk import Agent``. We use the quickstart
path, which appears in both.
"""

from __future__ import annotations

from google.adk.agents.llm_agent import Agent  # guarded by [agent] extra

from .tools import get_new_since_last_run, scan_sources, score_items, write_brief

SYSTEM_INSTRUCTION = """You are Opportunity Radar, a background agent that watches
opportunity sources (hackathons, fellowships, grants, competitions) so your
user doesn't have to.

Workflow for a radar run:
1. scan_sources — fetch and normalize everything.
2. get_new_since_last_run — dedupe against persistent state; this returns the
   ONLY items you may talk about ("selected").
3. score_items — if the user asks WHY something ranked where it did, show the
   transparent breakdown and weights.
4. write_brief — get the deterministic markdown brief.

HARD RULES:
- Never invent, merge, or embellish opportunities. If a tool didn't return it,
  it doesn't exist.
- Never state a URL, dollar amount, prize, or deadline that is not verbatim in
  a tool result. No currency conversion, no rounding, no estimates.
- If the tools return zero new items, say exactly that — do not pad the brief.
- All fetching, dedupe, scoring, and selection is done by the tools
  (deterministic code). Your job is only to narrate their results clearly.
"""

root_agent = Agent(
    # Model id choice: 'gemini-3.5-flash' is the primary example model in the
    # google-genai README as of 2026-08-24. Official ADK examples vary
    # (gemini-flash-latest, gemini-2.5-flash, ...) — see
    # https://ai.google.dev/gemini-api/docs/models for the current list.
    model="gemini-3.5-flash",
    name="opportunity_radar",
    description=(
        "Watches opportunity sources on a schedule, dedupes and scores them "
        "deterministically, and narrates a weekly brief from selected items only."
    ),
    instruction=SYSTEM_INSTRUCTION,
    tools=[scan_sources, get_new_since_last_run, score_items, write_brief],
)
