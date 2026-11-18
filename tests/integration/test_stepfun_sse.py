"""StepFun ASR client against a local SSE server."""

from __future__ import annotations

import pytest

from fmk.errors import ProviderError
from fmk.providers.stepfun import StepFunAsr
from tests.fixtures.sse_server import sse_server


def test_normal_stream_concatenates_and_uses_done_text() -> None:
    with sse_server("normal") as url:
        provider = StepFunAsr("test-key", endpoint=url, timeout=5, trust_env=False)
        assert provider.transcribe(b"\x00\x00") == "你好世界"


def test_truncated_stream_keeps_partial_text() -> None:
    with sse_server("truncated") as url:
        provider = StepFunAsr("test-key", endpoint=url, timeout=5, trust_env=False)
        assert provider.transcribe(b"\x00\x00") == "部分"


def test_error_event_raises_provider_error() -> None:
    with sse_server("error") as url:
        provider = StepFunAsr("test-key", endpoint=url, timeout=5, trust_env=False)
        with pytest.raises(ProviderError, match="boom"):
            provider.transcribe(b"\x00\x00")


def test_missing_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("FMK_STEPFUN_API_KEY", raising=False)
    provider = StepFunAsr(trust_env=False)
    with pytest.raises(ProviderError, match="FMK_STEPFUN_API_KEY"):
        provider.transcribe(b"\x00\x00")
