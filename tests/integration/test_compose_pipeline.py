"""End-to-end preflight → transcribe → compose on synthetic audio."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from fmk.config import load_config
from fmk.context import Context
from fmk.providers.base import MinuteRef
from fmk.state import StateStore
from fmk.steps.compose import ComposeStep
from fmk.steps.preflight import PreflightStep
from fmk.steps.transcribe import TranscribeStep

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
FAKE_FFMPEG = FIXTURES / "fake_ffmpeg"
GOLDEN = FIXTURES / "golden" / "single.md"
TOKEN = "aaaaaaaaaaaaaaa1"


class FakeAsr:
    name = "stepfun"
    api_version = 1

    def transcribe(self, pcm: bytes) -> str:
        return f"片段{pcm.decode('ascii')}"


def test_pipeline_produces_golden_document(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        "[transcribe]\n"
        "segment_seconds = 8\n"
        "request_seconds = 4\n"
        "concurrency = 2\n"
        "max_retries = 1\n"
        "[preflight]\nmin_words = 1\n",
        encoding="utf-8",
    )
    config = load_config(config_path, env={})
    store = StateStore(config.workspace.state_dir / "state.json")
    store.load()
    context = Context(
        config,
        state=store,
        providers={"stepfun": FakeAsr()},
        options={
            "ffmpeg": str(FAKE_FFMPEG),
            "mean_volume": lambda path: -20.0,
            "sleep": lambda seconds: None,
        },
    )
    audio = tmp_path / "audio.ogg"
    audio.write_bytes(b"fake")
    context.set(
        "minutes.list",
        [
            MinuteRef(
                token=TOKEN,
                title="测试访谈",
                start=datetime(2026, 11, 17, 13, 2),
                duration_seconds=8,
                url="https://example.feishu.cn/minutes/aaaaaaaaaaaaaaa1",
                keywords=("产品", "增长"),
            )
        ],
        step="discover",
        provides=frozenset({"minutes.list"}),
    )
    context.set("audio.path", {TOKEN: audio}, step="download", provides=frozenset({"audio.path"}))

    PreflightStep().run(context)
    TranscribeStep().run(context)
    result = ComposeStep().run(context)

    documents = context.require("doc.path")
    assert documents[TOKEN] == config.workspace.work_dir / "docs" / f"{TOKEN}.md"
    assert documents[TOKEN].read_text(encoding="utf-8") == GOLDEN.read_text(encoding="utf-8")
    assert result.evidence["documents"] == 1
    assert context.state is not None
    item = context.state.state.items[TOKEN]
    assert item.status == "composed"
    assert item.words == 6
