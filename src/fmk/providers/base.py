"""Provider protocols and shared value objects."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Protocol, runtime_checkable

API_VERSION = 1


@dataclass(frozen=True)
class MinuteRef:
    """A minute returned by a search, before download."""

    token: str
    title: str
    start: datetime | None = None
    duration_seconds: int = 0
    url: str = ""
    keywords: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class MinuteMeta:
    """Metadata fetched for a single minute."""

    token: str
    title: str
    start: datetime | None = None
    duration_seconds: int = 0
    url: str = ""


@runtime_checkable
class MinutesProvider(Protocol):
    """Source of minutes and their audio."""

    name: str
    api_version: int

    def search(self, start: date, end: date) -> list[MinuteRef]: ...

    def meta(self, token: str) -> MinuteMeta: ...

    def download(self, token: str, dest: Path) -> Path | None: ...

    def official_transcript(self, token: str) -> str | None: ...


@runtime_checkable
class AsrProvider(Protocol):
    """Speech recogniser that turns 16 kHz mono PCM into text."""

    name: str
    api_version: int

    def transcribe(self, pcm: bytes) -> str: ...


@dataclass(frozen=True)
class PublishResult:
    committed: bool
    commit: str | None = None
    changed_files: int = 0


@runtime_checkable
class Publisher(Protocol):
    """Publish the archive to a remote destination."""

    name: str
    api_version: int

    def publish(
        self,
        archive_dir: Path,
        *,
        remote: str,
        branch: str,
        message: str,
        dry_run: bool = False,
    ) -> PublishResult: ...
