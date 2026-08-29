"""LocalJSONState: roundtrip, atomicity, corrupt-file tolerance."""

import json

from opportunity_radar.state import LocalJSONState


def test_roundtrip_seen_ids(tmp_path):
    path = tmp_path / "state.json"
    state = LocalJSONState(path)
    assert state.get_seen_ids() == set()
    state.add_seen_ids({"devpost:1", "devpost:2"})

    reloaded = LocalJSONState(path)
    assert reloaded.get_seen_ids() == {"devpost:1", "devpost:2"}


def test_seen_ids_merge_not_replace(tmp_path):
    path = tmp_path / "state.json"
    LocalJSONState(path).add_seen_ids({"a"})
    LocalJSONState(path).add_seen_ids({"b"})
    assert LocalJSONState(path).get_seen_ids() == {"a", "b"}


def test_last_run_roundtrip(tmp_path):
    path = tmp_path / "state.json"
    state = LocalJSONState(path)
    assert state.get_last_run() is None
    state.set_last_run("2026-08-25T12:00:00")
    assert LocalJSONState(path).get_last_run() == "2026-08-25T12:00:00"


def test_atomic_write_leaves_no_temp_files(tmp_path):
    path = tmp_path / "state.json"
    state = LocalJSONState(path)
    for i in range(5):
        state.add_seen_ids({f"id-{i}"})
    leftovers = [p for p in tmp_path.iterdir() if p.name != "state.json"]
    assert leftovers == []  # every write went through os.replace
    # and the final file is valid JSON with all ids
    data = json.loads(path.read_text())
    assert len(data["seen_ids"]) == 5


def test_corrupt_state_file_treated_as_empty(tmp_path):
    path = tmp_path / "state.json"
    path.write_text("{not json!!")
    state = LocalJSONState(path)
    assert state.get_seen_ids() == set()
    state.add_seen_ids({"x"})
    assert LocalJSONState(path).get_seen_ids() == {"x"}
