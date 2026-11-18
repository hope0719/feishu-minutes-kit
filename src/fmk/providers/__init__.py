"""Providers shipped with feishu-minutes-kit."""

from __future__ import annotations

from fmk.providers.base import (
    API_VERSION,
    AsrProvider,
    MinuteMeta,
    MinuteRef,
    MinutesProvider,
    Publisher,
    PublishResult,
)
from fmk.providers.git_publisher import GitPublisher
from fmk.providers.lark_cli import LarkCliProvider
from fmk.providers.stepfun import StepFunAsr

__all__ = [
    "API_VERSION",
    "AsrProvider",
    "GitPublisher",
    "LarkCliProvider",
    "MinuteMeta",
    "MinuteRef",
    "MinutesProvider",
    "Publisher",
    "PublishResult",
    "StepFunAsr",
    "builtin_providers",
]


def builtin_providers() -> list[object]:
    """Return the built-in provider instances."""

    return [LarkCliProvider(), StepFunAsr(), GitPublisher()]
