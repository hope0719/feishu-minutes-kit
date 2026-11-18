"""Transcript value objects shared by steps and renderers."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TranscriptSegment:
    """A composed paragraph with absolute offsets inside the recording."""

    index: int
    start: int
    end: int
    text: str
