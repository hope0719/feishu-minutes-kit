"""Pipeline ordering, validation and plan options."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from fmk.context import Context
from fmk.errors import ConfigError
from fmk.pipeline import Pipeline
from fmk.registry import Registry
from fmk.steps.base import StepResult


@dataclass(frozen=True)
class FakeStep:
    name: str
    requires: frozenset[str] = frozenset()
    provides: frozenset[str] = frozenset()
    api_version: int = 1

    def run(self, ctx: Context) -> StepResult:
        return StepResult(status="ok")


def _registry(*steps: FakeStep) -> Registry:
    registry = Registry()
    for step in steps:
        assert registry.register_step(step, source="test")
    return registry


def _linear() -> Registry:
    return _registry(
        FakeStep("a", provides=frozenset({"x"})),
        FakeStep("b", requires=frozenset({"x"}), provides=frozenset({"y"})),
        FakeStep("c", requires=frozenset({"y"}), provides=frozenset({"z"})),
    )


def test_plan_preserves_configured_order() -> None:
    pipeline = Pipeline(_linear(), ["a", "b", "c"])
    assert [step.name for step in pipeline.plan()] == ["a", "b", "c"]


def test_unknown_step_in_config() -> None:
    with pytest.raises(ConfigError, match="未知步骤"):
        Pipeline(_linear(), ["a", "missing"])


def test_duplicate_step_in_config() -> None:
    with pytest.raises(ConfigError, match="重复步骤"):
        Pipeline(_linear(), ["a", "a"])


def test_unsatisfied_requirement() -> None:
    registry = _registry(
        FakeStep("a", provides=frozenset({"x"})),
        FakeStep("b", requires=frozenset({"missing"})),
    )
    with pytest.raises(ConfigError, match="missing"):
        Pipeline(registry, ["a", "b"]).validate()


def test_cycle_detection() -> None:
    registry = _registry(
        FakeStep("x", requires=frozenset({"y"}), provides=frozenset({"x"})),
        FakeStep("y", requires=frozenset({"x"}), provides=frozenset({"y"})),
    )
    with pytest.raises(ConfigError, match="循环依赖"):
        Pipeline(registry, ["x", "y"]).validate()


def test_only_truncates_inclusive() -> None:
    pipeline = Pipeline(_linear(), ["a", "b", "c"])
    assert [step.name for step in pipeline.plan(only="b")] == ["a", "b"]


def test_only_unknown_step() -> None:
    pipeline = Pipeline(_linear(), ["a", "b", "c"])
    with pytest.raises(ConfigError, match="--only"):
        pipeline.plan(only="z")


def test_resume_skips_completed() -> None:
    pipeline = Pipeline(_linear(), ["a", "b", "c"])
    assert [step.name for step in pipeline.plan(resume=True, completed=["a"])] == ["b", "c"]


def test_plan_validates_before_filtering() -> None:
    registry = _registry(
        FakeStep("a", requires=frozenset({"missing"})),
        FakeStep("b", provides=frozenset({"z"})),
    )
    with pytest.raises(ConfigError, match="missing"):
        Pipeline(registry, ["a", "b"]).plan(only="b")
