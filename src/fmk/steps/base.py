"""Step protocol and result value objects."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal, Protocol, runtime_checkable

from fmk.errors import StepError

if TYPE_CHECKING:
    from fmk.context import Context

API_VERSION = 1

Status = Literal["ok", "skip", "retry", "fail"]


@dataclass(frozen=True)
class StepResult:
    """Outcome of a single step run."""

    status: Status
    outputs: Mapping[str, Any] = field(default_factory=dict)
    reason: str | None = None
    evidence: Mapping[str, Any] = field(default_factory=dict)


@runtime_checkable
class Step(Protocol):
    """Contract every pipeline step must satisfy."""

    @property
    def api_version(self) -> int: ...

    @property
    def name(self) -> str: ...

    @property
    def requires(self) -> frozenset[str]: ...

    @property
    def provides(self) -> frozenset[str]: ...

    def run(self, ctx: Context) -> StepResult: ...


@dataclass(frozen=True)
class PlaceholderStep:
    """Declared but not yet implemented built-in step."""

    name: str
    requires: frozenset[str]
    provides: frozenset[str]
    api_version: int = API_VERSION

    def run(self, ctx: Context) -> StepResult:
        raise StepError(f"步骤 {self.name} 尚未实现", hint="该步骤将在后续里程碑补齐")
