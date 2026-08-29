"""Shared test fixtures. Tests never import any google package and never
touch the network — the Devpost source is only exercised via FixtureSource."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from opportunity_radar.scoring import load_profile
from opportunity_radar.sources import FixtureSource

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "devpost_sample.json"

# Frozen clock matching the fixture's reference date (injected — the pipeline
# never reads the wall clock).
NOW = datetime(2026, 8, 25, 12, 0, 0)


@pytest.fixture
def fixture_path() -> Path:
    return FIXTURE_PATH


@pytest.fixture
def items() -> list[dict]:
    return FixtureSource(FIXTURE_PATH).fetch()


@pytest.fixture
def profile() -> dict:
    return load_profile(Path(__file__).parents[1] / "profile.example.yaml")


@pytest.fixture
def now() -> datetime:
    return NOW
