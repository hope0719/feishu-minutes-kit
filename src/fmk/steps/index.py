"""Build quote, number and people indexes from the archive."""

from __future__ import annotations

from pathlib import Path

from fmk.context import Context
from fmk.core.indexes import render_indexes
from fmk.core.naming import scan_archive
from fmk.providers.base import API_VERSION
from fmk.steps.base import StepResult

QUOTES_NAME = "_quotes.md"
NUMBERS_NAME = "_numbers.md"
PEOPLE_NAME = "_people.md"


class IndexStep:
    """Write three mechanical indexes and skip cleanly when disabled."""

    api_version = API_VERSION
    name = "index"
    requires: frozenset[str] = frozenset({"archive.path"})
    provides: frozenset[str] = frozenset({"index.files"})

    def run(self, ctx: Context) -> StepResult:
        ctx.require("archive.path")
        archive = ctx.config.workspace.archive_dir
        if not ctx.config.index.enabled:
            ctx.set("index.files", {}, step=self.name, provides=self.provides)
            ctx.logger.info("index: 已在配置中关闭，跳过")
            return StepResult(
                status="skip",
                outputs={"index.files": {}},
                reason="index.enabled=false",
            )

        items = scan_archive(archive)
        quotes, numbers, people = render_indexes(items, archive)
        contents = {
            QUOTES_NAME: quotes,
            NUMBERS_NAME: numbers,
            PEOPLE_NAME: people,
        }
        paths: dict[str, Path] = {}
        for name, text in contents.items():
            path = archive / name
            paths[name] = path
            if not ctx.dry_run:
                archive.mkdir(parents=True, exist_ok=True)
                path.write_text(text, encoding="utf-8")

        ctx.set("index.files", paths, step=self.name, provides=self.provides)
        ctx.logger.info("index: 基于 %d 篇成稿生成三类索引", len(items))
        return StepResult(
            status="ok",
            outputs={"index.files": paths},
            evidence={"documents": len(items), "files": len(paths), "dry_run": ctx.dry_run},
        )
