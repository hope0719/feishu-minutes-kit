"""Plugin discovery for built-in and third-party steps and providers."""

from __future__ import annotations

import importlib.metadata
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from fmk.errors import ConfigError
from fmk.providers import builtin_providers
from fmk.steps import builtin_steps
from fmk.steps.base import API_VERSION, Step

STEP_GROUP = "fmk.steps"
PROVIDER_GROUP = "fmk.providers"


@dataclass(frozen=True)
class PluginRecord:
    name: str
    kind: str
    source: str
    module: str


class Registry:
    """Collect steps and providers, rejecting incompatible plugins."""

    def __init__(self) -> None:
        self._steps: dict[str, Step] = {}
        self._providers: dict[str, Any] = {}
        self._records: list[PluginRecord] = []
        self.warnings: list[str] = []

    def _warn(self, message: str) -> None:
        self.warnings.append(message)

    def register_step(self, step: Any, *, source: str) -> bool:
        name = getattr(step, "name", None)
        if not isinstance(name, str) or not name:
            self._warn(f"{source} 提供的步骤缺少 name，已跳过")
            return False
        version = getattr(step, "api_version", None)
        if version != API_VERSION:
            self._warn(f"步骤 {name} 的 api_version={version!r} 不匹配，已跳过")
            return False
        if not isinstance(step, Step):
            self._warn(f"步骤 {name} 未实现 Step 协议，已跳过")
            return False
        if name in self._steps:
            self._warn(f"步骤 {name} 重名，保留先注册的来源 {self._steps[name]!r}")
            return False
        self._steps[name] = step
        self._records.append(
            PluginRecord(name=name, kind="step", source=source, module=type(step).__module__)
        )
        return True

    def register_provider(self, provider: Any, *, source: str) -> bool:
        name = getattr(provider, "name", None)
        if not isinstance(name, str) or not name:
            self._warn(f"{source} 提供的 provider 缺少 name，已跳过")
            return False
        version = getattr(provider, "api_version", None)
        if version != API_VERSION:
            self._warn(f"provider {name} 的 api_version={version!r} 不匹配，已跳过")
            return False
        if name in self._providers:
            self._warn(f"provider {name} 重名，保留先注册的来源 {self._providers[name]!r}")
            return False
        self._providers[name] = provider
        self._records.append(
            PluginRecord(
                name=name, kind="provider", source=source, module=type(provider).__module__
            )
        )
        return True

    def discover(
        self,
        *,
        entry_points: Mapping[str, Iterable[Any]] | None = None,
        include_builtin: bool = True,
    ) -> None:
        """Register built-in components and load entry point plugins.

        ``entry_points`` may be injected in tests; otherwise the installed
        distribution metadata is read.
        """

        if include_builtin:
            for step in builtin_steps():
                self.register_step(step, source="builtin")
            for provider in builtin_providers():
                self.register_provider(provider, source="builtin")

        groups = (
            {
                STEP_GROUP: list(entry_points.get(STEP_GROUP, ())),
                PROVIDER_GROUP: list(entry_points.get(PROVIDER_GROUP, ())),
            }
            if entry_points is not None
            else {
                STEP_GROUP: _load_entry_points(STEP_GROUP),
                PROVIDER_GROUP: _load_entry_points(PROVIDER_GROUP),
            }
        )

        for entry_point in groups[STEP_GROUP]:
            self._load_one(entry_point, kind="step")
        for entry_point in groups[PROVIDER_GROUP]:
            self._load_one(entry_point, kind="provider")

    def _load_one(self, entry_point: Any, *, kind: str) -> None:
        label = getattr(entry_point, "name", "?")
        source = getattr(entry_point, "value", label)
        try:
            obj = entry_point.load()
        except Exception as exc:  # noqa: BLE001 - plugin import must never be fatal
            self._warn(f"插件 {label} 导入失败，已跳过: {type(exc).__name__}: {exc}")
            return
        if kind == "step":
            self.register_step(obj, source=str(source))
        else:
            self.register_provider(obj, source=str(source))

    def get_step(self, name: str) -> Step:
        try:
            return self._steps[name]
        except KeyError as exc:
            raise ConfigError(f"未知步骤: {name}") from exc

    @property
    def steps(self) -> list[Step]:
        return list(self._steps.values())

    @property
    def providers(self) -> dict[str, Any]:
        return dict(self._providers)

    @property
    def records(self) -> list[PluginRecord]:
        return sorted(self._records, key=lambda record: (record.kind, record.name))


def _load_entry_points(group: str) -> list[Any]:
    entry_points: Any = importlib.metadata.entry_points()
    select = getattr(entry_points, "select", None)
    if callable(select):
        return list(select(group=group))
    return list(entry_points.get(group, ()))
