"""Plugin discovery and rejection rules."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from fmk.context import Context
from fmk.errors import ConfigError
from fmk.registry import Registry
from fmk.steps import builtin_steps
from fmk.steps.base import StepResult


@dataclass(frozen=True)
class FakeStep:
    name: str
    requires: frozenset[str] = frozenset()
    provides: frozenset[str] = frozenset()
    api_version: int = 1

    def run(self, ctx: Context) -> StepResult:
        return StepResult(status="ok")


class FakeEntryPoint:
    def __init__(self, name: str, obj: Any = None, error: Exception | None = None) -> None:
        self.name = name
        self.value = f"fake:{name}"
        self._obj = obj
        self._error = error

    def load(self) -> Any:
        if self._error is not None:
            raise self._error
        return self._obj


class FakeProvider:
    name = "fake-provider"
    api_version = 1


def test_builtin_steps_are_discovered() -> None:
    registry = Registry()
    registry.discover(entry_points={})
    names = [step.name for step in registry.steps]
    assert names == [step.name for step in builtin_steps()]
    assert names[0] == "discover"
    assert len(names) == 9


def test_third_party_step_is_registered() -> None:
    registry = Registry()
    registry.discover(entry_points={"fmk.steps": [FakeEntryPoint("custom", FakeStep("custom"))]})
    assert registry.get_step("custom").name == "custom"
    assert any(record.kind == "step" for record in registry.records)


def test_api_version_mismatch_is_skipped() -> None:
    registry = Registry()
    registry.discover(
        entry_points={"fmk.steps": [FakeEntryPoint("bad", FakeStep("bad", api_version=2))]}
    )
    assert "bad" not in [step.name for step in registry.steps]
    assert any("api_version" in warning for warning in registry.warnings)


def test_duplicate_name_keeps_first() -> None:
    registry = Registry()
    registry.discover(entry_points={"fmk.steps": [FakeEntryPoint("dup", FakeStep("download"))]})
    assert any("重名" in warning for warning in registry.warnings)
    assert not isinstance(registry.get_step("download"), FakeStep)


def test_import_failure_is_not_fatal() -> None:
    registry = Registry()
    registry.discover(
        entry_points={"fmk.steps": [FakeEntryPoint("broken", error=ImportError("boom"))]}
    )
    assert len(registry.steps) == 9
    assert any("导入失败" in warning for warning in registry.warnings)


def test_provider_entry_point_is_listed() -> None:
    registry = Registry()
    registry.discover(
        entry_points={"fmk.providers": [FakeEntryPoint("fake-provider", FakeProvider())]}
    )
    assert "fake-provider" in registry.providers
    assert any(record.kind == "provider" for record in registry.records)


def test_unknown_step_raises_config_error() -> None:
    with pytest.raises(ConfigError, match="未知步骤"):
        Registry().get_step("nope")
