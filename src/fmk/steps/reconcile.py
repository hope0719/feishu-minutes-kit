"""Reconcile the transcript queue against archive and audio folders."""

from __future__ import annotations

from datetime import date, timedelta

from fmk.context import Context
from fmk.core.audio import find_audio
from fmk.core.naming import scan_archive
from fmk.core.queue import QueueReport, QueueRow, write_queue
from fmk.providers.base import API_VERSION
from fmk.steps.base import StepResult

ACTIVE_STATUSES = frozenset({"discovered", "downloaded", "transcribed", "failed"})
RECENT_DAYS = 14


class ReconcileStep:
    """Write ``_queue.md`` with four-way statistics and duplicate warnings."""

    api_version = API_VERSION
    name = "reconcile"
    requires: frozenset[str] = frozenset({"archive.path"})
    provides: frozenset[str] = frozenset({"queue.status"})

    def run(self, ctx: Context) -> StepResult:
        ctx.require("archive.path")
        archive = ctx.config.workspace.archive_dir
        items = scan_archive(archive)
        archive_tokens = {item.token for item in items}

        counts: dict[str, int] = {}
        for item in items:
            counts[item.token] = counts.get(item.token, 0) + 1
        duplicates = tuple(sorted(token for token, count in counts.items() if count > 1))

        audio_tokens = (
            {
                child.name
                for child in ctx.config.workspace.minutes_dir.iterdir()
                if child.is_dir() and find_audio(child) is not None
            }
            if ctx.config.workspace.minutes_dir.is_dir()
            else set()
        )

        pending_rows: list[QueueRow] = []
        with_audio = 0
        missing_audio = 0
        if ctx.state is not None:
            for token, state_item in ctx.state.state.items.items():
                if state_item.status not in ACTIVE_STATUSES or token in archive_tokens:
                    continue
                pending_rows.append(
                    QueueRow(
                        token=token,
                        status=state_item.status,
                        updated_at=state_item.updated_at or "",
                    )
                )
                if token in audio_tokens:
                    with_audio += 1
                else:
                    missing_audio += 1
        pending_rows.sort(key=lambda row: (row.status, row.token))

        cutoff = date.today() - timedelta(days=RECENT_DAYS)
        recent = sorted(
            (item for item in items if item.recorded_at.date() >= cutoff),
            key=lambda item: item.recorded_at,
            reverse=True,
        )
        history = sorted(
            (item for item in items if item.recorded_at.date() < cutoff),
            key=lambda item: item.recorded_at,
            reverse=True,
        )

        report = QueueReport(
            total_docs=len(items),
            done=len(items),
            pending=len(pending_rows),
            with_audio=with_audio,
            missing_audio=missing_audio,
            orphan_audio=len(audio_tokens - archive_tokens),
            duplicates=duplicates,
            pending_rows=pending_rows,
            recent=recent,
            history=history,
        )

        if not ctx.dry_run:
            write_queue(archive, report)

        status = {
            "total_docs": report.total_docs,
            "done": report.done,
            "pending": report.pending,
            "with_audio": report.with_audio,
            "missing_audio": report.missing_audio,
            "orphan_audio": report.orphan_audio,
            "duplicates": list(report.duplicates),
            "recent": len(report.recent),
            "history": len(report.history),
        }
        ctx.set("queue.status", status, step=self.name, provides=self.provides)
        ctx.logger.info(
            "reconcile: 成稿 %d，待转 %d，孤立音频 %d，重复 token %d",
            report.total_docs,
            report.pending,
            report.orphan_audio,
            len(report.duplicates),
        )
        return StepResult(status="ok", outputs={"queue.status": status}, evidence=status)
