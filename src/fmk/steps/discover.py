"""Discover new minutes while excluding everything already archived."""

from __future__ import annotations

import re
from datetime import date, timedelta

from fmk.context import Context
from fmk.core.audio import find_audio
from fmk.errors import ConfigError
from fmk.providers.base import API_VERSION, MinuteRef, MinutesProvider
from fmk.state import TERMINAL_STATUSES
from fmk.steps.base import StepResult

TOKEN_RE = re.compile(r"/minutes/([a-z0-9]{15,})")
DEFAULT_WINDOW_DAYS = 7


def known_tokens(ctx: Context) -> set[str]:
    """Collect tokens that are already archived, downloaded or settled in state."""

    known: set[str] = set()
    workspace = ctx.config.workspace

    if workspace.archive_dir.is_dir():
        for path in workspace.archive_dir.rglob("*.md"):
            text = path.read_text(encoding="utf-8", errors="ignore")[:4000]
            known.update(TOKEN_RE.findall(text))

    if workspace.minutes_dir.is_dir():
        for child in workspace.minutes_dir.iterdir():
            if child.is_dir() and find_audio(child) is not None:
                known.add(child.name)

    queue = workspace.archive_dir / "_queue.md"
    if queue.is_file():
        known.update(TOKEN_RE.findall(queue.read_text(encoding="utf-8", errors="ignore")))

    if ctx.state is not None:
        for token, item in ctx.state.state.items.items():
            if item.status in TERMINAL_STATUSES:
                known.add(token)

    return known


def search_window(ctx: Context) -> tuple[date, date]:
    """Compute the inclusive date window from CLI options and last search."""

    today = date.today()
    raw_since = ctx.option("since")
    if raw_since:
        if isinstance(raw_since, date):
            return raw_since, today
        try:
            return date.fromisoformat(str(raw_since)), today
        except ValueError as exc:
            raise ConfigError(
                f"--since 不是合法日期: {raw_since!r}", hint="格式为 YYYY-MM-DD"
            ) from exc

    if ctx.state is not None and ctx.state.state.last_search:
        try:
            last = date.fromisoformat(ctx.state.state.last_search)
            return last - timedelta(days=2), today
        except ValueError:
            pass
    return today - timedelta(days=DEFAULT_WINDOW_DAYS), today


class DiscoverStep:
    """List minutes that are not present in any known source."""

    api_version = API_VERSION
    name = "discover"
    requires: frozenset[str] = frozenset()
    provides: frozenset[str] = frozenset({"minutes.list"})

    def run(self, ctx: Context) -> StepResult:
        provider_name = ctx.config.source.provider
        provider = ctx.provider(provider_name)
        if not isinstance(provider, MinutesProvider):
            raise ConfigError(f"provider {provider_name} 未实现 MinutesProvider 协议")

        since, until = search_window(ctx)
        fetched = provider.search(since, until)
        known = known_tokens(ctx)

        new: list[MinuteRef] = []
        seen: set[str] = set()
        for item in sorted(fetched, key=_sort_key, reverse=True):
            if item.token in seen or item.token in known:
                continue
            seen.add(item.token)
            new.append(item)

        ctx.set("minutes.list", new, step=self.name, provides=self.provides)
        ctx.logger.info(
            "discover: %s → %s，获取 %d 条，已知 %d 条，新增 %d 条",
            since.isoformat(),
            until.isoformat(),
            len(fetched),
            len(known),
            len(new),
        )
        return StepResult(
            status="ok",
            outputs={"minutes.list": new},
            evidence={
                "since": since.isoformat(),
                "until": until.isoformat(),
                "fetched": len(fetched),
                "known": len(known),
                "new": len(new),
            },
        )


def _sort_key(ref: MinuteRef) -> float:
    return ref.start.timestamp() if ref.start is not None else float("-inf")
