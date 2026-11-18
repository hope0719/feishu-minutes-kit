"""Error types and their CLI exit codes."""

from __future__ import annotations

from typing import Final

EXIT_OK: Final = 0
EXIT_CONFIG: Final = 2
EXIT_PARTIAL: Final = 3
EXIT_VERIFICATION: Final = 4


class FmkError(Exception):
    """Base class for failures the CLI knows how to report."""

    exit_code: int = EXIT_CONFIG

    def __init__(self, message: str, *, hint: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.hint = hint

    def render(self) -> str:
        if self.hint:
            return f"{self.message}\n提示: {self.hint}"
        return self.message


class ConfigError(FmkError):
    """Invalid configuration or missing environment."""

    exit_code = EXIT_CONFIG


class ProviderError(FmkError):
    """An external source, ASR or publisher call failed."""

    exit_code = EXIT_PARTIAL


class StepError(FmkError):
    """A pipeline step could not finish."""

    exit_code = EXIT_PARTIAL


class VerificationError(FmkError):
    """Produced artifacts do not meet the acceptance rules."""

    exit_code = EXIT_VERIFICATION
