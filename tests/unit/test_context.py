"""Context namespace isolation."""

from __future__ import annotations

from pathlib import Path

import pytest

from fmk.config import load_config
from fmk.context import Context
from fmk.errors import StepError


@pytest.fixture
def ctx(tmp_path: Path) -> Context:
    config_path = tmp_path / "config.toml"
    config_path.write_text("", encoding="utf-8")
    return Context(load_config(config_path, env={}))


def test_read_write_declared_key(ctx: Context) -> None:
    ctx.set("minutes.list", [1, 2], step="discover", provides=frozenset({"minutes.list"}))
    assert ctx.get("minutes.list") == [1, 2]
    assert ctx.require("minutes.list") == [1, 2]
    assert ctx.owner("minutes.list") == "discover"
    assert ctx.keys() == frozenset({"minutes.list"})


def test_write_undeclared_key_rejected(ctx: Context) -> None:
    with pytest.raises(StepError, match="不允许写入"):
        ctx.set("other", 1, step="discover", provides=frozenset({"minutes.list"}))


def test_cannot_overwrite_other_step_output(ctx: Context) -> None:
    ctx.set("minutes.list", [1], step="discover", provides=frozenset({"minutes.list"}))
    with pytest.raises(StepError, match="不能覆盖"):
        ctx.set("minutes.list", [2], step="download", provides=frozenset({"minutes.list"}))


def test_same_step_may_update_its_own_key(ctx: Context) -> None:
    ctx.set("minutes.list", [1], step="discover", provides=frozenset({"minutes.list"}))
    ctx.set("minutes.list", [1, 2], step="discover", provides=frozenset({"minutes.list"}))
    assert ctx.get("minutes.list") == [1, 2]


def test_require_missing_key(ctx: Context) -> None:
    with pytest.raises(StepError, match="缺少上下文键"):
        ctx.require("missing")
