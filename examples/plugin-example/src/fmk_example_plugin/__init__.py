"""Example third-party step: count characters in composed documents."""

from __future__ import annotations

from pathlib import Path

from fmk.context import Context
from fmk.steps.base import StepResult

API_VERSION = 1


class WordCountStep:
    """Read ``doc.path`` and expose character counts as ``doc.words``."""

    api_version = API_VERSION
    name = "wordcount"
    requires: frozenset[str] = frozenset({"doc.path"})
    provides: frozenset[str] = frozenset({"doc.words"})

    def run(self, ctx: Context) -> StepResult:
        docs: dict[str, Path] = dict(ctx.require("doc.path"))
        counts = {
            token: len(path.read_text(encoding="utf-8", errors="ignore"))
            for token, path in docs.items()
            if path.is_file()
        }
        ctx.set("doc.words", counts, step=self.name, provides=self.provides)
        return StepResult(status="ok", outputs={"doc.words": counts})
