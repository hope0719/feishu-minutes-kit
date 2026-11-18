"""Execution context shared by pipeline steps."""

from __future__ import annotations

import logging as _logging
from collections.abc import Collection, Mapping
from typing import Any

from fmk.config import Config
from fmk.errors import ConfigError, StepError
from fmk.logging import get_logger
from fmk.state import StateStore


class Context:
    """Namespaced data bag with write ownership checks.

    A step may only write the keys it declared in ``provides`` and may never
    overwrite a value produced by another step.
    """

    def __init__(
        self,
        config: Config,
        *,
        state: StateStore | None = None,
        dry_run: bool = False,
        logger: _logging.Logger | None = None,
        providers: Mapping[str, Any] | None = None,
        options: Mapping[str, Any] | None = None,
    ) -> None:
        self.config = config
        self.state = state
        self.dry_run = dry_run
        self.logger = logger or get_logger()
        self.providers = dict(providers or {})
        self.options = dict(options or {})
        self._data: dict[str, Any] = {}
        self._owners: dict[str, str] = {}

    def provider(self, name: str) -> Any:
        try:
            return self.providers[name]
        except KeyError as exc:
            raise ConfigError(
                f"未找到 provider: {name}",
                hint="检查配置中的 source.provider，或安装并启用对应插件",
            ) from exc

    def option(self, name: str, default: Any = None) -> Any:
        return self.options.get(name, default)

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def require(self, key: str) -> Any:
        try:
            return self._data[key]
        except KeyError as exc:
            raise StepError(f"缺少上下文键 {key}", hint="请检查步骤的 requires 声明") from exc

    def set(self, key: str, value: Any, *, step: str, provides: Collection[str]) -> None:
        if key not in provides:
            raise StepError(
                f"步骤 {step} 不允许写入 {key}",
                hint="只能写入自己在 provides 中声明的键",
            )
        owner = self._owners.get(key)
        if owner is not None and owner != step:
            raise StepError(f"上下文键 {key} 已被步骤 {owner} 写入，{step} 不能覆盖")
        self._data[key] = value
        self._owners[key] = step

    def owner(self, key: str) -> str | None:
        return self._owners.get(key)

    def keys(self) -> frozenset[str]:
        return frozenset(self._data)

    def snapshot(self) -> dict[str, Any]:
        return dict(self._data)
