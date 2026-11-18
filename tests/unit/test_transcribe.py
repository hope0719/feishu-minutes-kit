"""Slice caching, retries and paragraph grouping."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from fmk.config import load_config
from fmk.context import Context
from fmk.errors import ProviderError
from fmk.providers.base import MinuteRef
from fmk.state import StateStore
from fmk.steps.preflight import PreflightVerdict
from fmk.steps.transcribe import TranscribeStep

FAKE_FFMPEG = Path(__file__).resolve().parents[1] / "fixtures" / "fake_ffmpeg"
TOKEN = "aaaaaaaaaaaaaaa1"


class FakeAsr:
    name = "stepfun"
    api_version = 1

    def __init__(self) -> None:
        self.calls = 0

    def transcribe(self, pcm: bytes) -> str:
        self.calls += 1
        return f"片段{pcm.decode('ascii')}"


class FlakyAsr(FakeAsr):
    def __init__(self, fail_times: int) -> None:
        super().__init__()
        self.fail_times = fail_times

    def transcribe(self, pcm: bytes) -> str:
        self.calls += 1
        if self.calls <= self.fail_times:
            raise ProviderError("temporary failure")
        return f"片段{pcm.decode('ascii')}"


class AlwaysFailAsr(FakeAsr):
    def transcribe(self, pcm: bytes) -> str:
        self.calls += 1
        raise ProviderError("always fails")


def _context(tmp_path: Path, provider: object) -> Context:
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        "[transcribe]\n"
        "segment_seconds = 8\n"
        "request_seconds = 4\n"
        "concurrency = 2\n"
        "max_retries = 2\n"
        "[preflight]\nmin_words = 1\n",
        encoding="utf-8",
    )
    config = load_config(config_path, env={})
    store = StateStore(config.workspace.state_dir / "state.json")
    store.load()
    context = Context(
        config,
        state=store,
        providers={"stepfun": provider},
        options={"ffmpeg": str(FAKE_FFMPEG), "sleep": lambda seconds: None},
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
            )
        ],
        step="discover",
        provides=frozenset({"minutes.list"}),
    )
    context.set("audio.path", {TOKEN: audio}, step="download", provides=frozenset({"audio.path"}))
    context.set(
        "preflight.verdict",
        {TOKEN: PreflightVerdict("ok", "测试访谈", -20.0)},
        step="preflight",
        provides=frozenset({"preflight.verdict"}),
    )
    return context


def test_transcribes_slices_and_caches(tmp_path: Path) -> None:
    provider = FakeAsr()
    context = _context(tmp_path, provider)
    TranscribeStep().run(context)

    segments = context.require("transcript.segments")
    assert len(segments[TOKEN]) == 1
    segment = segments[TOKEN][0]
    assert (segment.index, segment.start, segment.end) == (1, 0, 8)
    assert segment.text == "片段0片段4"
    assert context.state is not None
    assert context.state.state.items[TOKEN].status == "transcribed"
    assert context.state.state.items[TOKEN].words == 6

    seg_dir = context.config.workspace.minutes_dir / TOKEN / "_segs"
    assert (seg_dir / "000000.txt").read_text(encoding="utf-8") == "片段0"
    assert (seg_dir / "000004.txt").read_text(encoding="utf-8") == "片段4"

    calls = provider.calls
    second = _context(tmp_path, provider)
    TranscribeStep().run(second)
    assert provider.calls == calls
    assert second.require("transcript.segments")[TOKEN][0].text == "片段0片段4"


def test_retries_failed_slice(tmp_path: Path) -> None:
    provider = FlakyAsr(fail_times=1)
    context = _context(tmp_path, provider)
    TranscribeStep().run(context)

    segments = context.require("transcript.segments")
    assert segments[TOKEN][0].text == "片段0片段4"
    assert provider.calls == 3


def test_all_slices_failing_marks_item_failed(tmp_path: Path) -> None:
    provider = AlwaysFailAsr()
    context = _context(tmp_path, provider)
    result = TranscribeStep().run(context)

    assert context.require("transcript.segments") == {}
    assert result.evidence["failed"] == 1
    assert context.state is not None
    assert context.state.state.items[TOKEN].status == "failed"
