"""Compose Markdown documents from transcript segments."""

from __future__ import annotations

from pathlib import Path

from fmk.context import Context
from fmk.core.markdown import render_document, word_count
from fmk.core.transcript import TranscriptSegment
from fmk.errors import VerificationError
from fmk.providers.base import API_VERSION, MinuteRef
from fmk.state import ItemState
from fmk.steps.base import StepResult


class ComposeStep:
    """Write one Markdown file per transcribed minute."""

    api_version = API_VERSION
    name = "compose"
    requires: frozenset[str] = frozenset({"transcript.segments"})
    provides: frozenset[str] = frozenset({"doc.path"})

    def run(self, ctx: Context) -> StepResult:
        segments_map: dict[str, list[TranscriptSegment]] = dict(ctx.require("transcript.segments"))
        items = {item.token: item for item in ctx.require("minutes.list")}
        docs_dir = ctx.config.workspace.work_dir / "docs"
        asr_label = f"{ctx.config.asr.provider} {ctx.config.asr.model}"

        docs: dict[str, Path] = {}
        updates: dict[str, ItemState] = {}

        for token, segments in segments_map.items():
            item: MinuteRef | None = items.get(token)
            if item is None:
                raise VerificationError(f"妙记 {token} 缺少元数据，无法成稿")
            if item.start is None:
                raise VerificationError(f"妙记 {token} 缺少录制时间，无法成稿")

            document = render_document(
                title=item.title,
                start=item.start,
                duration_seconds=item.duration_seconds,
                url=item.url,
                asr_label=asr_label,
                segments=segments,
                keywords=item.keywords,
            )
            path = docs_dir / f"{token}.md"
            docs[token] = path
            if ctx.dry_run:
                continue
            docs_dir.mkdir(parents=True, exist_ok=True)
            path.write_text(document, encoding="utf-8")
            updates[token] = ItemState(
                status="composed", words=word_count(segments), files=[str(path)]
            )

        if ctx.state is not None and updates and not ctx.dry_run:
            ctx.state.update_items(updates)

        ctx.set("doc.path", docs, step=self.name, provides=self.provides)
        ctx.logger.info("compose: 生成 %d 篇成稿", len(docs))
        return StepResult(
            status="ok",
            outputs={"doc.path": docs},
            evidence={"documents": len(docs), "dry_run": ctx.dry_run},
        )
