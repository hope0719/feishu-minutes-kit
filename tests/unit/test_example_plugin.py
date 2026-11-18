"""The bundled example plugin loads as a valid step."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

from fmk.config import load_config
from fmk.context import Context
from fmk.registry import Registry

EXAMPLE = (
    Path(__file__).resolve().parents[2]
    / "examples"
    / "plugin-example"
    / "src"
    / "fmk_example_plugin"
    / "__init__.py"
)


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("fmk_example_plugin", EXAMPLE)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_example_step_is_discoverable_and_runs(tmp_path: Path) -> None:
    module = _load()
    registry = Registry()
    registry.discover(entry_points={})
    assert registry.register_step(module.WordCountStep(), source="example")

    config_path = tmp_path / "config.toml"
    config_path.write_text("", encoding="utf-8")
    context = Context(load_config(config_path, env={}))
    doc = tmp_path / "doc.md"
    doc.write_text("你好", encoding="utf-8")
    context.set("doc.path", {"token": doc}, step="compose", provides=frozenset({"doc.path"}))

    result = module.WordCountStep().run(context)
    assert result.status == "ok"
    assert context.require("doc.words") == {"token": 2}
