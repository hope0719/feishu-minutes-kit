"""Markdown document rendering."""

from __future__ import annotations

import re
from collections.abc import Sequence
from datetime import datetime

from fmk.core.transcript import TranscriptSegment
from fmk.errors import VerificationError


def hms(seconds: int) -> str:
    return f"{seconds // 3600:02d}:{seconds % 3600 // 60:02d}:{seconds % 60:02d}"


def human_duration(seconds: int) -> str:
    hours, minutes, secs = seconds // 3600, seconds % 3600 // 60, seconds % 60
    prefix = f"{hours} 小时 " if hours else ""
    return f"{prefix}{minutes} 分 {secs} 秒"


def word_count(segments: Sequence[TranscriptSegment]) -> int:
    return sum(len(re.sub(r"\s", "", segment.text)) for segment in segments)


def _validate_segments(segments: Sequence[TranscriptSegment]) -> None:
    previous_end: int | None = None
    for position, segment in enumerate(segments, start=1):
        if segment.index != position:
            raise VerificationError(f"段落编号不连续：期望 {position}，实际 {segment.index}")
        if segment.end <= segment.start:
            raise VerificationError(f"第 {segment.index} 段结束时间不大于开始时间")
        if previous_end is not None and segment.start != previous_end:
            raise VerificationError(f"第 {segment.index} 段与上一段时间不连续")
        previous_end = segment.end


def render_document(
    *,
    title: str,
    start: datetime,
    duration_seconds: int,
    url: str,
    asr_label: str,
    segments: Sequence[TranscriptSegment],
    keywords: Sequence[str] = (),
    official_words: int | None = None,
) -> str:
    """Render a finished Markdown document with six fixed header fields."""

    _validate_segments(segments)
    words = word_count(segments)
    official = (
        f"{official_words} 字，仅作核对，正文未使用"
        if official_words is not None
        else "未获取，正文未使用"
    )

    lines = [
        f"# {start.month}月{start.day}日 · {title}",
        "",
        f"> 录制时间：{start.year}-{start.month:02d}-{start.day:02d} "
        f"{start.hour:02d}:{start.minute:02d} ｜ 时长：{human_duration(duration_seconds)}",
        f"> 妙记：{url}",
        "",
        f"- 正文来源：{asr_label} 重转",
        f"- 正文字数：{words}",
        f"- 原妙记标题：{title}",
        f"- 妙记官方逐字稿：{official}",
    ]
    if keywords:
        lines.append("- 关键词：" + "、".join(keywords))
    lines += [
        "",
        f"> 说明：正文由 {asr_label} 对下载的原音频重新转录，不使用妙记官方逐字稿。",
        "",
        "---",
        "",
    ]
    for segment in segments:
        lines += [
            f"## 第 {segment.index} 段 ｜ 录音 {hms(segment.start)} – {hms(segment.end)}",
            "",
            segment.text.strip(),
            "",
        ]
    return "\n".join(lines)
