"""Opportunity Radar — an async agent that watches opportunity sources so you don't have to.

Deterministic Python owns fetching, parsing, dedupe, scoring, and selection.
The model (Gemini) only writes narrative from already-selected items, and its
output must pass an anti-invention gate before it is returned.
"""

__version__ = "0.1.0"
