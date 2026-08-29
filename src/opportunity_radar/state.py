"""Persistent state for dedupe across runs.

Two implementations of the same interface:

- LocalJSONState — default, atomic writes, fully tested offline.
- FirestoreState — DRAFT / UNTESTED. Written for Cloud Run Jobs deployment,
  guarded import so the base install never needs google-cloud-firestore.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path


class State:
    """Interface for radar persistent state (seen ids + last run timestamp)."""

    def get_seen_ids(self) -> set[str]:  # pragma: no cover - interface
        raise NotImplementedError

    def add_seen_ids(self, ids: set[str]) -> None:  # pragma: no cover - interface
        raise NotImplementedError

    def get_last_run(self) -> str | None:  # pragma: no cover - interface
        raise NotImplementedError

    def set_last_run(self, iso_timestamp: str) -> None:  # pragma: no cover - interface
        raise NotImplementedError


class LocalJSONState(State):
    """JSON-file state with atomic writes (write temp file, then os.replace).

    A crash mid-write can never corrupt the state file: readers only ever see
    the previous complete version or the new complete version.
    """

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self._data = self._load()

    def _load(self) -> dict:
        if self.path.exists():
            try:
                return json.loads(self.path.read_text())
            except json.JSONDecodeError:
                # Corrupt state is treated as empty rather than crashing the run;
                # atomic writes make this path unreachable in practice.
                return {"seen_ids": [], "last_run": None}
        return {"seen_ids": [], "last_run": None}

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(
            dir=str(self.path.parent), prefix=self.path.name, suffix=".tmp"
        )
        try:
            with os.fdopen(fd, "w") as f:
                json.dump(self._data, f, indent=2, sort_keys=True)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_path, self.path)
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)

    def get_seen_ids(self) -> set[str]:
        return set(self._data.get("seen_ids", []))

    def add_seen_ids(self, ids: set[str]) -> None:
        merged = self.get_seen_ids() | set(ids)
        self._data["seen_ids"] = sorted(merged)
        self._save()

    def get_last_run(self) -> str | None:
        return self._data.get("last_run")

    def set_last_run(self, iso_timestamp: str) -> None:
        self._data["last_run"] = iso_timestamp
        self._save()


class FirestoreState(State):
    """DRAFT — UNTESTED. Firestore-backed state for Cloud Run Jobs.

    Requires ``pip install "opportunity-radar[gcp]"`` and application-default
    credentials (or a service account on Cloud Run). Never imported by tests.
    Document layout: collection ``opportunity_radar``, doc ``{doc_id}`` with
    fields ``seen_ids: list[str]`` and ``last_run: str``.
    """

    def __init__(self, project: str | None = None, doc_id: str = "default"):
        try:
            from google.cloud import firestore  # type: ignore
        except ImportError as e:  # pragma: no cover - guarded optional dep
            raise ImportError(
                "FirestoreState requires the [gcp] extra: "
                'pip install "opportunity-radar[gcp]"'
            ) from e
        self._client = firestore.Client(project=project)
        self._ref = self._client.collection("opportunity_radar").document(doc_id)

    def _read(self) -> dict:  # pragma: no cover - DRAFT, untested
        snap = self._ref.get()
        return snap.to_dict() if snap.exists else {"seen_ids": [], "last_run": None}

    def get_seen_ids(self) -> set[str]:  # pragma: no cover - DRAFT, untested
        return set(self._read().get("seen_ids", []))

    def add_seen_ids(self, ids: set[str]) -> None:  # pragma: no cover - DRAFT, untested
        merged = sorted(self.get_seen_ids() | set(ids))
        self._ref.set({"seen_ids": merged}, merge=True)

    def get_last_run(self) -> str | None:  # pragma: no cover - DRAFT, untested
        return self._read().get("last_run")

    def set_last_run(self, iso_timestamp: str) -> None:  # pragma: no cover - DRAFT, untested
        self._ref.set({"last_run": iso_timestamp}, merge=True)
