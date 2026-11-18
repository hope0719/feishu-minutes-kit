"""Logging helpers with mandatory secret redaction."""

from __future__ import annotations

import logging as _logging
import re

REDACTED = "****"

_AUTHORIZATION = re.compile(
    r"(?i)\b(authorization\s*[:=]\s*)(bearer\s+)?([^\s,;]+)",
)
_KEY_VALUE = re.compile(
    r"(?i)(\b[0-9a-z_]*(?:api[_-]?key|apikey|token|secret|password)[0-9a-z_]*\s*[=:]\s*)([^\s,;&]+)",
)
_QUERY = re.compile(r"(?i)([?&](?:token|access_token|api_key|api-key)=)([^&\s]+)")


def _mask_authorization(match: re.Match[str]) -> str:
    prefix, scheme, _ = match.group(1), match.group(2) or "", match.group(3)
    return f"{prefix}{scheme}{REDACTED}"


def redact(text: str) -> str:
    """Replace credentials in *text* with a fixed mask."""

    text = _AUTHORIZATION.sub(_mask_authorization, text)
    text = _KEY_VALUE.sub(lambda m: f"{m.group(1)}{REDACTED}", text)
    return _QUERY.sub(lambda m: f"{m.group(1)}{REDACTED}", text)


def mask_secret(value: str | None) -> str:
    """Return a display-safe form of a credential."""

    if not value:
        return "未设置"
    if len(value) <= 4:
        return REDACTED
    return f"{value[:4]}{REDACTED}"


class RedactionFilter(_logging.Filter):
    """Filter that strips secrets from log records before formatting."""

    def filter(self, record: _logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
        except Exception:  # pragma: no cover - malformed record, leave as-is
            return True
        record.msg = redact(message)
        record.args = ()
        return True


def get_logger(name: str = "fmk", level: int | None = None) -> _logging.Logger:
    """Return a logger with the redaction filter attached exactly once."""

    logger = _logging.getLogger(name)
    if level is not None:
        logger.setLevel(level)
    if not any(isinstance(f, RedactionFilter) for f in logger.filters):
        logger.addFilter(RedactionFilter())
    return logger
