"""Pipeline planning: order, dependency validation and cycle detection."""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from fmk.errors import ConfigError
from fmk.registry import Registry
from fmk.steps.base import Step


class Pipeline:
    """Validate and plan execution of named steps."""

    def __init__(self, registry: Registry, order: Sequence[str]) -> None:
        self.registry = registry
        self.order = tuple(order)
        if not self.order:
            raise ConfigError("配置项 pipeline.steps 不能为空")
        if len(set(self.order)) != len(self.order):
            raise ConfigError("配置项 pipeline.steps 存在重复步骤")
        unknown = [name for name in self.order if name not in {s.name for s in registry.steps}]
        if unknown:
            raise ConfigError(f"配置项 pipeline.steps 包含未知步骤: {', '.join(unknown)}")

    def validate(self) -> None:
        self._check_cycles()
        available: set[str] = set()
        for name in self.order:
            step = self.registry.get_step(name)
            missing = step.requires - available
            if missing:
                raise ConfigError(
                    f"步骤 {name} 依赖的 {', '.join(sorted(missing))} 未被前序步骤提供"
                )
            available.update(step.provides)

    def _check_cycles(self) -> None:
        provider_of: dict[str, str] = {}
        for name in self.order:
            for key in self.registry.get_step(name).provides:
                provider_of.setdefault(key, name)

        graph: dict[str, set[str]] = {name: set() for name in self.order}
        for name in self.order:
            for key in self.registry.get_step(name).requires:
                provider = provider_of.get(key)
                if provider is not None and provider != name:
                    graph[name].add(provider)

        state: dict[str, int] = {}
        stack: list[str] = []

        def visit(node: str) -> None:
            state[node] = 1
            stack.append(node)
            for neighbour in graph[node]:
                if state.get(neighbour) == 1:
                    cycle = stack[stack.index(neighbour) :] + [neighbour]
                    raise ConfigError("步骤存在循环依赖: " + " → ".join(cycle))
                if state.get(neighbour, 0) == 0:
                    visit(neighbour)
            stack.pop()
            state[node] = 2

        for node in self.order:
            if state.get(node, 0) == 0:
                visit(node)

    def plan(
        self,
        *,
        only: str | None = None,
        resume: bool = False,
        completed: Iterable[str] = (),
    ) -> list[Step]:
        self.validate()
        steps = [self.registry.get_step(name) for name in self.order]
        if only is not None:
            if only not in self.order:
                raise ConfigError(f"--only 指定的步骤不在流水线中: {only}")
            steps = steps[: self.order.index(only) + 1]
        if resume:
            done = set(completed)
            steps = [step for step in steps if step.name not in done]
        return steps
