"""Preflight duplicate and silence decisions."""

from __future__ import annotations

from pathlib import Path

from fmk.config import load_config
from fmk.context import Context
from fmk.providers.base import MinuteRef
from fmk.state import StateStore
from fmk.steps.preflight import DUP_RE, PreflightStep


def _context(tmp_path: Path, levels: dict[str, float]) -> Context:
    config_path = tmp_path / "config.toml"
    config_path.write_text("", encoding="utf-8")
    config = load_config(config_path, env={})
    store = StateStore(config.workspace.state_dir / "state.json")
    store.load()
    context = Context(
        config,
        state=store,
        options={"mean_volume": lambda path: levels[path.name]},
    )
    items = [
        MinuteRef("token-duplicate", "重复录像 · 测试"),
        MinuteRef("token-silent", "产品周会"),
        MinuteRef("token-ok", "客户访谈"),
    ]
    audio = {
        "token-duplicate": tmp_path / "duplicate.ogg",
        "token-silent": tmp_path / "silent.ogg",
        "token-ok": tmp_path / "ok.ogg",
    }
    context.set("minutes.list", items, step="discover", provides=frozenset({"minutes.list"}))
    context.set("audio.path", audio, step="download", provides=frozenset({"audio.path"}))
    return context


def test_duplicate_title_wins_over_silence(tmp_path: Path) -> None:
    context = _context(
        tmp_path,
        {"duplicate.ogg": -70.0, "silent.ogg": -70.0, "ok.ogg": -20.0},
    )
    result = PreflightStep().run(context)
    verdicts = context.require("preflight.verdict")

    assert verdicts["token-duplicate"].status == "duplicate"
    assert verdicts["token-silent"].status == "silent"
    assert verdicts["token-ok"].status == "ok"
    assert result.evidence["counts"] == {"ok": 1, "duplicate": 1, "silent": 1, "no-audio": 0}


def test_skip_states_are_recorded(tmp_path: Path) -> None:
    context = _context(
        tmp_path,
        {"duplicate.ogg": -20.0, "silent.ogg": -55.0, "ok.ogg": -20.0},
    )
    PreflightStep().run(context)
    assert context.state is not None

    assert context.state.state.items["token-duplicate"].status == "duplicate"
    silent = context.state.state.items["token-silent"]
    assert silent.status == "silent"
    assert silent.mean_db == -55.0
    assert "token-ok" not in context.state.state.items


def test_duplicate_pattern() -> None:
    assert DUP_RE.search("重复录像 · 10月1日")
    assert DUP_RE.search("xx重复碎片")
    assert not DUP_RE.search("产品周会")


def test_missing_audio_is_marked(tmp_path: Path) -> None:
    context = _context(tmp_path, {"duplicate.ogg": -20.0, "silent.ogg": -20.0, "ok.ogg": -20.0})
    context.set(
        "audio.path",
        {"token-ok": tmp_path / "ok.ogg"},
        step="download",
        provides=frozenset({"audio.path"}),
    )
    PreflightStep().run(context)
    verdicts = context.require("preflight.verdict")
    assert verdicts["token-silent"].status == "no-audio"
    assert verdicts["token-duplicate"].status == "duplicate"
