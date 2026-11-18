"""Log redaction and credential masking."""

from __future__ import annotations

import logging

from fmk.logging import RedactionFilter, mask_secret, redact


def test_redact_authorization_header() -> None:
    output = redact("Authorization: Bearer sk-live-abc123")
    assert "sk-live-abc123" not in output
    assert output.endswith("****")


def test_redact_api_key_assignment() -> None:
    output = redact("FMK_STEPFUN_API_KEY=sk-test-9999")
    assert "sk-test-9999" not in output
    assert "FMK_STEPFUN_API_KEY=" in output


def test_redact_query_token() -> None:
    output = redact("GET /minutes?token=abc123&limit=10")
    assert "abc123" not in output
    assert "limit=10" in output


def test_mask_secret() -> None:
    assert mask_secret(None) == "未设置"
    assert mask_secret("") == "未设置"
    assert mask_secret("abcd1234") == "abcd****"
    assert mask_secret("abc") == "****"


def test_filter_masks_formatted_message() -> None:
    record = logging.LogRecord(
        name="fmk.test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="api_key=%s",
        args=("sk-secret-value",),
        exc_info=None,
    )
    assert RedactionFilter().filter(record) is True
    assert "sk-secret-value" not in record.getMessage()
