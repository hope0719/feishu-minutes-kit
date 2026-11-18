"""Persistent run state stored as JSON with a schema version."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from fmk.errors import ConfigError

SCHEMA_VERSION = 1
STATE_FILENAME = "state.json"

TERMINAL_STATUSES = frozenset(
    {
        "composed",
        "organized",
        "reconciled",
        "indexed",
        "published",
        "silent",
        "duplicate",
        "empty",
        "no-audio",
        "abandoned",
    }
)


class _CorruptState(Exception):
    """Internal marker for unreadable state files."""


@dataclass
class ItemState:
    status: str
    attempts: int = 0
    words: int | None = None
    mean_db: float | None = None
    files: list[str] = field(default_factory=list)
    reason: str | None = None
    updated_at: str | None = None


@dataclass
class State:
    last_run: str | None = None
    last_search: str | None = None
    completed_steps: set[str] = field(default_factory=set)
    items: dict[str, ItemState] = field(default_factory=dict)


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _parse_item(raw: Any) -> ItemState:
    if not isinstance(raw, dict):
        raise _CorruptState
    status = raw.get("status")
    if not isinstance(status, str) or not status:
        raise _CorruptState
    attempts = raw.get("attempts", 0)
    words = raw.get("words")
    mean_db = raw.get("mean_db")
    files = raw.get("files", [])
    reason = raw.get("reason")
    updated_at = raw.get("updated_at")
    if isinstance(attempts, bool) or not isinstance(attempts, int):
        raise _CorruptState
    if words is not None and (isinstance(words, bool) or not isinstance(words, int)):
        raise _CorruptState
    if mean_db is not None and (isinstance(mean_db, bool) or not isinstance(mean_db, (int, float))):
        raise _CorruptState
    if not isinstance(files, list) or not all(isinstance(f, str) for f in files):
        raise _CorruptState
    if reason is not None and not isinstance(reason, str):
        raise _CorruptState
    if updated_at is not None and not isinstance(updated_at, str):
        raise _CorruptState
    return ItemState(
        status=status,
        attempts=attempts,
        words=words,
        mean_db=float(mean_db) if mean_db is not None else None,
        files=list(files),
        reason=reason,
        updated_at=updated_at,
    )


def _deserialize(raw: Any) -> State:
    if not isinstance(raw, dict):
        raise _CorruptState
    version = raw.get("schema_version")
    if version != SCHEMA_VERSION:
        raise ConfigError(
            f"状态文件 schema_version 不受支持: {version!r}（期望 {SCHEMA_VERSION}）",
            hint="请先运行迁移命令或从备份恢复；本工具不做静默兼容",
        )
    items_raw = raw.get("items", {})
    if not isinstance(items_raw, dict):
        raise _CorruptState
    completed = raw.get("completed_steps", [])
    if not isinstance(completed, list) or not all(isinstance(s, str) for s in completed):
        raise _CorruptState
    last_run = raw.get("last_run")
    last_search = raw.get("last_search")
    if last_run is not None and not isinstance(last_run, str):
        raise _CorruptState
    if last_search is not None and not isinstance(last_search, str):
        raise _CorruptState
    return State(
        last_run=last_run,
        last_search=last_search,
        completed_steps=set(completed),
        items={token: _parse_item(item) for token, item in items_raw.items()},
    )


def _serialize(state: State) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "last_run": state.last_run,
        "last_search": state.last_search,
        "completed_steps": sorted(state.completed_steps),
        "items": {token: asdict(item) for token, item in state.items.items()},
    }


class StateStore:
    """Load and atomically persist the run state."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.state = State()
        self.backup_path: Path | None = None

    def load(self) -> State:
        if not self.path.is_file():
            self.state = State()
            return self.state
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            self.state = _deserialize(raw)
        except (_CorruptState, json.JSONDecodeError, UnicodeDecodeError):
            self.backup_path = self._backup()
            self.state = State()
        return self.state

    def _backup(self) -> Path:
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup = self.path.with_name(f"{self.path.name}.corrupt-{stamp}")
        os.replace(self.path, backup)
        return backup

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(_serialize(self.state), ensure_ascii=False, indent=2) + "\n"
        temp = self.path.with_name(f".{self.path.name}.tmp")
        with temp.open("w", encoding="utf-8") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, self.path)

    def mark_step(self, name: str) -> None:
        self.state.completed_steps.add(name)
        self.state.last_run = _now()
        self.save()

    def update_item(self, token: str, item: ItemState) -> None:
        item.updated_at = _now()
        self.state.items[token] = item
        self.save()

    def update_items(self, items: dict[str, ItemState]) -> None:
        """Update several items and persist once."""

        now = _now()
        for token, item in items.items():
            item.updated_at = now
            self.state.items[token] = item
        self.save()
