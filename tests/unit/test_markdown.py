"""Markdown rendering against a golden file."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from fmk.core.markdown import render_document
from fmk.core.transcript import TranscriptSegment
from fmk.errors import VerificationError

GOLDEN = Path(__file__).resolve().parents[1] / "fixtures" / "golden" / "single.md"


def test_render_matches_golden() -> None:
    document = render_document(
        title="测试访谈",
        start=datetime(2026, 11, 17, 13, 2),
        duration_seconds=8,
        url="https://example.feishu.cn/minutes/aaaaaaaaaaaaaaa1",
        asr_label="stepfun stepaudio-2.5-asr",
        segments=[TranscriptSegment(1, 0, 8, "片段0片段4")],
        keywords=("产品", "增长"),
    )
    assert document == GOLDEN.read_text(encoding="utf-8")


def test_discontinuous_segments_are_rejected() -> None:
    segments = [
        TranscriptSegment(1, 0, 4, "第一段"),
        TranscriptSegment(2, 5, 8, "第二段"),
    ]
    with pytest.raises(VerificationError, match="不连续"):
        render_document(
            title="测试",
            start=datetime(2026, 11, 17, 13, 2),
            duration_seconds=8,
            url="",
            asr_label="stepfun stepaudio-2.5-asr",
            segments=segments,
        )


def test_segment_numbers_must_start_at_one() -> None:
    with pytest.raises(VerificationError, match="编号"):
        render_document(
            title="测试",
            start=datetime(2026, 11, 17, 13, 2),
            duration_seconds=8,
            url="",
            asr_label="stepfun stepaudio-2.5-asr",
            segments=[TranscriptSegment(2, 0, 8, "内容")],
        )
