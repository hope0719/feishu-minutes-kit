"""Queue reconciliation rendering."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from fmk.core.naming import ArchiveItem

STATUS_START = "<!-- fmk:status:start -->"
STATUS_END = "<!-- fmk:status:end -->"
QUEUE_NAME = "_queue.md"
HISTORY_NAME = "_queue-history.md"


@dataclass(frozen=True)
class QueueRow:
    token: str
    status: str
    updated_at: str


@dataclass(frozen=True)
class QueueReport:
    total_docs: int
    done: int
    pending: int
    with_audio: int
    missing_audio: int
    orphan_audio: int
    duplicates: tuple[str, ...]
    pending_rows: Sequence[QueueRow]
    recent: Sequence[ArchiveItem]
    history: Sequence[ArchiveItem]

    def render_block(self, archive_dir: Path) -> str:
        lines = [
            STATUS_START,
            "# 转录队列",
            "",
            f"- 队列条目 **{self.total_docs}** ｜ 已出稿 **{self.done}** ｜ 待转 **{self.pending}**"
            f"（有音频 {self.with_audio} / 缺音频 {self.missing_audio}）",
            f"- 有音频但无成稿 **{self.orphan_audio}** 条",
            "",
            "## 待转",
            "",
        ]
        if self.pending_rows:
            lines += ["| token | 状态 | 更新时间 |", "|---|---|---|"]
            for row in self.pending_rows:
                lines.append(f"| {row.token} | {row.status} | {row.updated_at or '—'} |")
        else:
            lines.append("无。")

        lines += ["", "## 近 14 天完成", ""]
        if self.recent:
            lines += ["| 日期 | 标题 | 文件 |", "|---|---|---|"]
            for item in self.recent:
                rel = _relative(item.path, archive_dir)
                lines.append(
                    f"| {item.recorded_at.date().isoformat()} | {item.title} | "
                    f"[{item.path.stem}]({rel}) |"
                )
        else:
            lines.append("无。")

        if self.duplicates:
            lines += ["", "## 重复发布告警", ""]
            for token in self.duplicates:
                lines.append(f"- `{token}` 出现了多篇成稿，请人工核对")
        lines.append(STATUS_END)
        return "\n".join(lines) + "\n"


def render_history(history: Sequence[ArchiveItem], archive_dir: Path) -> str:
    lines = ["# 队列历史", "", "> 超过 14 天的已完成条目。", ""]
    if not history:
        lines.append("暂无。")
    else:
        lines += ["| 日期 | 标题 | 文件 |", "|---|---|---|"]
        for item in history:
            lines.append(
                f"| {item.recorded_at.date().isoformat()} | {item.title} | "
                f"[{item.path.stem}]({_relative(item.path, archive_dir)}) |"
            )
    return "\n".join(lines) + "\n"


def _relative(path: Path, archive_dir: Path) -> str:
    try:
        return path.relative_to(archive_dir).as_posix()
    except ValueError:
        return path.name


def write_queue(archive_dir: Path, report: QueueReport) -> list[Path]:
    """Replace the marked status block and rewrite the history file."""

    archive_dir.mkdir(parents=True, exist_ok=True)
    queue = archive_dir / QUEUE_NAME
    block = report.render_block(archive_dir)

    if queue.is_file():
        text = queue.read_text(encoding="utf-8")
        start = text.find(STATUS_START)
        end = text.find(STATUS_END)
        if start >= 0 and end > start:
            prefix = text[:start].rstrip("\n")
            suffix = text[end + len(STATUS_END) :].strip("\n")
            parts = [part for part in (prefix, block.rstrip("\n"), suffix) if part]
            text = "\n\n".join(parts) + "\n"
        else:
            text = "# 转录队列\n\n" + block
    else:
        text = "# 转录队列\n\n" + block
    queue.write_text(text, encoding="utf-8")

    history = archive_dir / HISTORY_NAME
    history.write_text(render_history(report.history, archive_dir), encoding="utf-8")
    return [queue, history]
