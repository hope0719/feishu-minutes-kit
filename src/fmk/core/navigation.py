"""Deterministic navigation files for the archive."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from fmk.core.naming import ArchiveItem


@dataclass(frozen=True)
class NavEntry:
    item: ArchiveItem
    path: Path
    month_dir: str


def _month_label(month_dir: str) -> str:
    parts = month_dir.split("-")
    return f"{parts[1]} 年 {int(parts[2])} 月"


def render_month_index(month_dir: str, entries: Sequence[NavEntry]) -> str:
    total_words = sum(entry.item.words for entry in entries)
    lines = [
        f"# 妙记转录索引 · {_month_label(month_dir)}",
        "",
        f"> 共 {len(entries)} 篇 ｜ 正文合计 {total_words:,} 字",
        "",
        "| 日期 | 标题 | 时长 | 字数 | 正文来源 | 文件 |",
        "|---|---|---|---|---|---|",
    ]
    for entry in entries:
        item = entry.item
        date_label = f"{item.recorded_at.month}月{item.recorded_at.day}日"
        link = f"[{entry.path.stem}]({entry.path.name})"
        lines.append(
            f"| {date_label} | {item.title} | {item.duration_label} | "
            f"{item.words} | {item.source_label} | {link} |"
        )
    return "\n".join(lines) + "\n"


def render_overview(entries: Sequence[NavEntry]) -> str:
    if not entries:
        return "# 妙记转录总览\n\n> 暂无成稿。\n"

    groups: dict[str, list[NavEntry]] = {}
    for entry in entries:
        groups.setdefault(entry.month_dir, []).append(entry)
    ordered = sorted(groups.items(), key=lambda pair: pair[1][0].item.recorded_at, reverse=True)

    dates = [entry.item.recorded_at for entry in entries]
    first, last = min(dates), max(dates)
    lines = [
        "# 妙记转录总览",
        "",
        f"> 收录 **{len(entries)} 篇**转录"
        f"（{first.date().isoformat()} → {last.date().isoformat()}）",
        "",
        "## 月份目录",
        "",
        "| 月份 | 篇数 | 索引 |",
        "|---|---|---|",
    ]
    for month_dir, bucket in ordered:
        lines.append(
            f"| {month_dir} | {len(bucket)} | [{month_dir}/_index.md]({month_dir}/_index.md) |"
        )

    for month_dir, bucket in ordered:
        lines += ["", f"## {_month_label(month_dir)}（{len(bucket)} 篇）", ""]
        for entry in bucket:
            label = f"{entry.item.recorded_at.date().isoformat()} · {entry.item.title}"
            lines.append(f"- [{label}]({month_dir}/{entry.path.name})")
    return "\n".join(lines) + "\n"


def write_navigation(archive_dir: Path, entries: Sequence[NavEntry]) -> list[Path]:
    """Write ``_overview.md`` and one ``_index.md`` per month; return paths."""

    written: list[Path] = []
    groups: dict[str, list[NavEntry]] = {}
    for entry in entries:
        groups.setdefault(entry.month_dir, []).append(entry)

    for month_dir, bucket in groups.items():
        folder = archive_dir / month_dir
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / "_index.md"
        path.write_text(render_month_index(month_dir, bucket), encoding="utf-8")
        written.append(path)

    overview = archive_dir / "_overview.md"
    overview.write_text(render_overview(entries), encoding="utf-8")
    written.append(overview)
    return written
