"""Error types and exit-code mapping."""

from __future__ import annotations

from fmk.errors import (
    EXIT_CONFIG,
    EXIT_PARTIAL,
    EXIT_VERIFICATION,
    ConfigError,
    FmkError,
    ProviderError,
    StepError,
    VerificationError,
)


def test_exit_codes() -> None:
    assert ConfigError.exit_code == EXIT_CONFIG == 2
    assert ProviderError.exit_code == EXIT_PARTIAL == 3
    assert StepError.exit_code == EXIT_PARTIAL == 3
    assert VerificationError.exit_code == EXIT_VERIFICATION == 4


def test_render_with_hint() -> None:
    error = FmkError("出错了", hint="这样修")
    assert "出错了" in error.render()
    assert "这样修" in error.render()


def test_render_without_hint() -> None:
    assert ConfigError("缺少配置").render() == "缺少配置"
