"""Archive naming, document header parsing and placement planning."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from fmk.config import NamingConfig
from fmk.errors import ConfigError, VerificationError

MONTH_DIR_RE = re.compile(r"^\d{2}-(\d{4})-(\d{2})$")
TOKEN_RE = re.compile(r"/minutes/([a-z0-9]{15,})")
RECORDED_RE = re.compile(r"录制时间：(\d{4})-(\d{2})-(\d{2})(?:[ T](\d{2}):(\d{2}))?")
WORDS_RE = re.compile(r"正文字数：(\d+)")
DURATION_RE = re.compile(r"时长：([^｜\n]+)")
SOURCE_RE = re.compile(r"正文来源[：:]\s*([^\n｜]+)")
TITLE_RE = re.compile(r"^#\s+\d{1,2}月\d{1,2}日\s*·\s*(.+)$", re.MULTILINE)
UNSAFE_RE = re.compile(r'[\\/:*?"<>|]')


@dataclass
class ArchiveItem:
    token: str
    path: Path
    recorded_at: datetime
    title: str
    url: str = ""
    words: int = 0
    duration_label: str = "—"
    source_label: str = "—"


@dataclass(frozen=True)
class Placement:
    item: ArchiveItem
    month_key: tuple[int, int]
    month_dir: str
    file_name: str


@dataclass(frozen=True)
class ParsedDocument:
    token: str | None
    title: str
    recorded_at: datetime
    words: int
    duration_label: str
    source_label: str


def sanitize_title(title: str, max_chars: int) -> str:
    cleaned = UNSAFE_RE.sub(" ", title)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned[:max_chars] or "未命名"


def parse_document(text: str, *, fallback_time: datetime) -> ParsedDocument:
    """Extract header fields from a composed Markdown document."""

    head = text[:2000]
    title_match = TITLE_RE.search(head)
    token_match = TOKEN_RE.search(head)
    recorded_match = RECORDED_RE.search(head)
    words_match = WORDS_RE.search(head)
    duration_match = DURATION_RE.search(head)
    source_match = SOURCE_RE.search(head)

    recorded_at = fallback_time
    if recorded_match:
        year, month, day, hour, minute = (int(part or 0) for part in recorded_match.groups())
        recorded_at = datetime(year, month, day, hour, minute)

    return ParsedDocument(
        token=token_match.group(1) if token_match else None,
        title=title_match.group(1).strip() if title_match else "",
        recorded_at=recorded_at,
        words=int(words_match.group(1)) if words_match else 0,
        duration_label=duration_match.group(1).strip() if duration_match else "—",
        source_label=source_match.group(1).strip() if source_match else "—",
    )


def scan_archive(archive_dir: Path) -> list[ArchiveItem]:
    """Read every composed document inside ``NN-YYYY-MM`` folders."""

    if not archive_dir.is_dir():
        return []
    items: list[ArchiveItem] = []
    for folder in sorted(archive_dir.iterdir()):
        if not (folder.is_dir() and MONTH_DIR_RE.match(folder.name)):
            continue
        for path in sorted(folder.glob("*.md")):
            if path.name.startswith("_"):
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            parsed = parse_document(
                text, fallback_time=datetime.fromtimestamp(path.stat().st_mtime)
            )
            if parsed.token is None:
                continue
            items.append(
                ArchiveItem(
                    token=parsed.token,
                    path=path,
                    recorded_at=parsed.recorded_at,
                    title=parsed.title or parsed.token,
                    words=parsed.words,
                    duration_label=parsed.duration_label,
                    source_label=parsed.source_label,
                )
            )
    return items


def plan_months(items: list[ArchiveItem], naming: NamingConfig) -> dict[tuple[int, int], str]:
    months = sorted(
        {(item.recorded_at.year, item.recorded_at.month) for item in items}, reverse=True
    )
    return {
        month: naming.dir_format.format(index=index, year=month[0], month=month[1])
        for index, month in enumerate(months, start=1)
    }


def _sort_key(item: ArchiveItem) -> tuple[float, str, str]:
    return (-item.recorded_at.timestamp(), item.title, item.token)


def _unique_name(name: str, used: set[str]) -> str:
    if name not in used:
        used.add(name)
        return name
    stem, dot, suffix = name.rpartition(".")
    if not dot:
        stem, suffix = name, ""
    counter = 2
    while True:
        candidate = f"{stem}（{counter}）" + (f".{suffix}" if suffix else "")
        if candidate not in used:
            used.add(candidate)
            return candidate
        counter += 1


def plan_placements(items: list[ArchiveItem], naming: NamingConfig) -> list[Placement]:
    months = plan_months(items, naming)
    groups: dict[tuple[int, int], list[ArchiveItem]] = {}
    for item in items:
        groups.setdefault((item.recorded_at.year, item.recorded_at.month), []).append(item)

    placements: list[Placement] = []
    for month, month_dir in months.items():
        used: set[str] = set()
        bucket = sorted(groups[month], key=_sort_key)
        for index, item in enumerate(bucket, start=1):
            title = sanitize_title(item.title, naming.max_title_chars)
            try:
                name = naming.file_format.format(
                    index=index,
                    date=item.recorded_at.date().isoformat(),
                    title=title,
                )
            except (KeyError, IndexError, ValueError) as exc:
                raise ConfigError(
                    f"配置项 naming.file_format 无法格式化: {naming.file_format!r}"
                ) from exc
            name = _unique_name(name, used)
            placements.append(
                Placement(item=item, month_key=month, month_dir=month_dir, file_name=name)
            )
    return placements


def ensure_unique_tokens(items: list[ArchiveItem]) -> None:
    seen: dict[str, Path] = {}
    for item in items:
        previous = seen.get(item.token)
        if previous is not None and previous != item.path:
            raise VerificationError(
                f"同一妙记出现多篇成稿: {item.token}",
                hint=f"请先处理 {previous} 与 {item.path}",
            )
        seen[item.token] = item.path
