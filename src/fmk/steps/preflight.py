"""Preflight: decide whether a minute should be transcribed."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from fmk.context import Context
from fmk.core.audio import mean_volume as default_mean_volume
from fmk.providers.base import API_VERSION, MinuteRef
from fmk.state import ItemState
from fmk.steps.base import StepResult

DUP_RE = re.compile(r"重复(录像|碎片|录音|录制)")

VerdictStatus = Literal["ok", "duplicate", "silent", "no-audio"]


@dataclass(frozen=True)
class PreflightVerdict:
    status: VerdictStatus
    title: str
    mean_db: float | None = None


class PreflightStep:
    """Check duplicate titles first, then average volume."""

    api_version = API_VERSION
    name = "preflight"
    requires: frozenset[str] = frozenset({"audio.path"})
    provides: frozenset[str] = frozenset({"preflight.verdict"})

    def run(self, ctx: Context) -> StepResult:
        items: list[MinuteRef] = list(ctx.require("minutes.list"))
        audio: dict[str, Path] = dict(ctx.require("audio.path"))

        measured = ctx.option("mean_volume")
        if callable(measured):
            measure: Callable[[Path], float] = measured
        else:
            ffmpeg = str(ctx.option("ffmpeg", "ffmpeg"))
            measure = lambda path: default_mean_volume(path, ffmpeg=ffmpeg)  # noqa: E731

        verdicts: dict[str, PreflightVerdict] = {}
        updates: dict[str, ItemState] = {}
        counts: dict[str, int] = {"ok": 0, "duplicate": 0, "silent": 0, "no-audio": 0}

        for item in items:
            token = item.token
            if DUP_RE.search(item.title):
                verdicts[token] = PreflightVerdict("duplicate", item.title)
                updates[token] = ItemState(status="duplicate", reason="标题标注为重复录像")
                counts["duplicate"] += 1
                continue

            path = audio.get(token)
            if path is None:
                verdicts[token] = PreflightVerdict("no-audio", item.title)
                counts["no-audio"] += 1
                continue

            level = float(measure(path))
            if level < ctx.config.preflight.silent_db:
                verdicts[token] = PreflightVerdict("silent", item.title, level)
                updates[token] = ItemState(
                    status="silent", mean_db=level, reason="平均音量低于阈值"
                )
                counts["silent"] += 1
                continue

            verdicts[token] = PreflightVerdict("ok", item.title, level)
            counts["ok"] += 1

        if ctx.state is not None and updates and not ctx.dry_run:
            ctx.state.update_items(updates)

        ctx.set("preflight.verdict", verdicts, step=self.name, provides=self.provides)
        ctx.logger.info(
            "preflight: 通过 %d，重复 %d，无声 %d，无音频 %d",
            counts["ok"],
            counts["duplicate"],
            counts["silent"],
            counts["no-audio"],
        )
        return StepResult(
            status="ok",
            outputs={"preflight.verdict": verdicts},
            evidence={"counts": counts},
        )
