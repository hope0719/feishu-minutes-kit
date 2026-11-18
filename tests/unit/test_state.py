"""State persistence, atomicity and corruption handling."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from fmk.errors import ConfigError
from fmk.state import SCHEMA_VERSION, ItemState, StateStore


def test_missing_file_returns_empty_state(tmp_path: Path) -> None:
    store = StateStore(tmp_path / "state.json")
    state = store.load()
    assert state.items == {}
    assert state.completed_steps == set()
    assert state.last_run is None


def test_save_and_reload_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    store = StateStore(path)
    store.load()
    store.state.items["token-a"] = ItemState(status="composed", words=120, files=["a.md"])
    store.mark_step("discover")

    reloaded = StateStore(path)
    state = reloaded.load()
    assert state.completed_steps == {"discover"}
    assert state.last_run is not None
    assert state.items["token-a"].status == "composed"
    assert state.items["token-a"].words == 120
    assert state.items["token-a"].files == ["a.md"]


def test_save_is_atomic_and_versioned(tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    store = StateStore(path)
    store.load()
    store.save()

    assert not list(tmp_path.glob(".state.json.tmp"))
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == SCHEMA_VERSION


def test_schema_mismatch_refuses_to_start(tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    path.write_text(json.dumps({"schema_version": 99, "items": {}}), encoding="utf-8")
    with pytest.raises(ConfigError, match="schema_version"):
        StateStore(path).load()


def test_corrupt_file_is_backed_up(tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    path.write_text("{not json", encoding="utf-8")
    store = StateStore(path)
    state = store.load()

    assert state.items == {}
    assert store.backup_path is not None
    assert store.backup_path.exists()
    assert not path.exists()


def test_update_item_sets_timestamp(tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    store = StateStore(path)
    store.load()
    store.update_item("token-b", ItemState(status="failed", attempts=2))

    reloaded = StateStore(path).load()
    item = reloaded.items["token-b"]
    assert item.attempts == 2
    assert item.updated_at is not None
