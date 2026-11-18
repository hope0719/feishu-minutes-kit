"""Download audio for discovered minutes and record per-item outcomes."""

from __future__ import annotations

from pathlib import Path

from fmk.context import Context
from fmk.core.audio import find_audio
from fmk.errors import ProviderError
from fmk.providers.base import API_VERSION, MinuteRef, MinutesProvider
from fmk.state import ItemState
from fmk.steps.base import StepResult


class DownloadStep:
    """Fetch audio files, reusing anything already on disk."""

    api_version = API_VERSION
    name = "download"
    requires: frozenset[str] = frozenset({"minutes.list"})
    provides: frozenset[str] = frozenset({"audio.path"})

    def run(self, ctx: Context) -> StepResult:
        items: list[MinuteRef] = list(ctx.require("minutes.list"))
        provider = ctx.provider(ctx.config.source.provider)
        if not isinstance(provider, MinutesProvider):
            raise ProviderError(f"provider {ctx.config.source.provider} 未实现 MinutesProvider")

        minutes_dir = ctx.config.workspace.minutes_dir
        # audio.path maps token -> local audio file for the current batch.
        paths: dict[str, Path] = {}
        updates: dict[str, ItemState] = {}
        planned: list[str] = []
        reused = 0
        failed = 0
        no_audio = 0

        for item in items:
            dest = minutes_dir / item.token
            existing = find_audio(dest)
            if existing is not None:
                paths[item.token] = existing
                reused += 1
                continue

            if ctx.dry_run:
                planned.append(item.token)
                continue

            try:
                path = provider.download(item.token, dest)
            except ProviderError as exc:
                failed += 1
                updates[item.token] = ItemState(status="failed", reason=str(exc))
                ctx.logger.warning("download: %s 下载失败：%s", item.title, exc)
                continue

            if path is None:
                no_audio += 1
                updates[item.token] = ItemState(status="no-audio", reason="下载后未找到音频文件")
                ctx.logger.warning("download: %s 没有可用音频", item.title)
                continue

            paths[item.token] = path
            updates[item.token] = ItemState(status="downloaded", files=[str(path)])

        if ctx.state is not None and updates and not ctx.dry_run:
            ctx.state.update_items(updates)

        ctx.set("audio.path", paths, step=self.name, provides=self.provides)

        downloaded = len(paths) - reused
        evidence = {
            "total": len(items),
            "reused": reused,
            "downloaded": downloaded,
            "no_audio": no_audio,
            "failed": failed,
            "planned": len(planned),
        }
        ctx.logger.info(
            "download: 共 %d 条，复用 %d，新下载 %d，无音频 %d，失败 %d",
            len(items),
            reused,
            downloaded,
            no_audio,
            failed,
        )
        return StepResult(status="ok", outputs={"audio.path": paths}, evidence=evidence)
