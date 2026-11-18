"""StepFun ASR provider using its SSE endpoint."""

from __future__ import annotations

import base64
import json
import os
from typing import Any

import httpx

from fmk.config import ENV_API_KEY
from fmk.errors import ProviderError
from fmk.logging import redact
from fmk.providers.base import API_VERSION

DEFAULT_ENDPOINT = "https://api.stepfun.com/step_plan/v1/audio/asr/sse"
DEFAULT_MODEL = "stepaudio-2.5-asr"


class StepFunAsr:
    """Stream PCM to StepFun and concatenate incremental transcript events."""

    name = "stepfun"
    api_version = API_VERSION

    def __init__(
        self,
        api_key: str | None = None,
        *,
        model: str = DEFAULT_MODEL,
        timeout: float = 120.0,
        endpoint: str = DEFAULT_ENDPOINT,
        trust_env: bool = True,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self.endpoint = endpoint
        self.trust_env = trust_env

    def with_config(
        self,
        *,
        api_key: str | None,
        model: str,
        timeout: float,
    ) -> StepFunAsr:
        return StepFunAsr(
            api_key,
            model=model,
            timeout=timeout,
            endpoint=self.endpoint,
            trust_env=self.trust_env,
        )

    def _key(self) -> str:
        key = self.api_key or os.environ.get(ENV_API_KEY, "")
        if not key.strip():
            raise ProviderError(
                "未设置 FMK_STEPFUN_API_KEY",
                hint="复制 .env.example 为 .env，或从环境变量注入",
            )
        return key

    def transcribe(self, pcm: bytes) -> str:
        payload: dict[str, Any] = {
            "audio": {
                "data": base64.b64encode(pcm).decode("ascii"),
                "input": {
                    "transcription": {
                        "model": self.model,
                        "language": "zh",
                        "enable_itn": True,
                    },
                    "format": {
                        "type": "pcm",
                        "codec": "pcm_s16le",
                        "rate": 16000,
                        "bits": 16,
                        "channel": 1,
                    },
                },
            }
        }
        headers = {
            "Authorization": f"Bearer {self._key()}",
            "Accept": "text/event-stream",
        }

        text = ""
        try:
            with (
                httpx.Client(timeout=self.timeout, trust_env=self.trust_env) as client,
                client.stream("POST", self.endpoint, json=payload, headers=headers) as response,
            ):
                if response.status_code >= 400:
                    raise ProviderError(
                        f"ASR 接口返回 HTTP {response.status_code}",
                        hint="检查凭证与额度后重试",
                    )
                for line in response.iter_lines():
                    line = line.strip()
                    if not line.startswith("data:"):
                        continue
                    raw = line[5:].strip()
                    if not raw or raw == "[DONE]":
                        continue
                    try:
                        event = json.loads(raw)
                    except json.JSONDecodeError:
                        continue
                    if not isinstance(event, dict):
                        continue
                    event_type = event.get("type")
                    if event_type == "transcript.text.done":
                        done_text = event.get("text")
                        if isinstance(done_text, str) and done_text:
                            text = done_text
                    elif event_type == "transcript.text.delta":
                        delta = event.get("delta")
                        if isinstance(delta, str):
                            text += delta
                    elif event_type == "error":
                        message = redact(str(event.get("message", "未知错误")))
                        raise ProviderError(f"ASR 错误事件: {message}")
        except httpx.HTTPError as exc:
            raise ProviderError(f"ASR 请求失败: {type(exc).__name__}") from exc

        if not text.strip():
            raise ProviderError("ASR 未返回文本")
        return text.strip()
