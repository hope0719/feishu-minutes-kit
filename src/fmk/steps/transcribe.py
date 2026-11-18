"""Transcribe audio in 120-second slices with on-disk caching."""

from __future__ import annotations

import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from fmk.context import Context
from fmk.core.audio import extract_pcm
from fmk.core.markdown import word_count
from fmk.core.transcript import TranscriptSegment
from fmk.errors import ConfigError, ProviderError
from fmk.providers.base import API_VERSION, AsrProvider, MinuteRef
from fmk.providers.stepfun import StepFunAsr
from fmk.state import ItemState
from fmk.steps.base import StepResult
from fmk.steps.preflight import PreflightVerdict


class TranscribeStep:
    """Slice audio, reuse cached text, then group slices into paragraphs."""

    api_version = API_VERSION
    name = "transcribe"
    requires: frozenset[str] = frozenset({"preflight.verdict"})
    provides: frozenset[str] = frozenset({"transcript.segments"})

    def run(self, ctx: Context) -> StepResult:
        verdicts: dict[str, PreflightVerdict] = dict(ctx.require("preflight.verdict"))
        items = {item.token: item for item in ctx.require("minutes.list")}
        audio: dict[str, Path] = dict(ctx.require("audio.path"))

        provider = self._provider(ctx)
        ffmpeg = str(ctx.option("ffmpeg", "ffmpeg"))
        sleep: Callable[[float], None] = ctx.option("sleep", time.sleep)
        config = ctx.config

        results: dict[str, list[TranscriptSegment]] = {}
        updates: dict[str, ItemState] = {}
        failed: list[str] = []
        empty: list[str] = []
        cached_total = 0
        requested_total = 0

        for token, verdict in verdicts.items():
            if verdict.status != "ok":
                continue
            item = items.get(token)
            path = audio.get(token)
            if item is None or path is None or item.duration_seconds <= 0:
                failed.append(token)
                updates[token] = ItemState(status="failed", reason="缺少音频、时长或妙记信息")
                continue

            seg_dir = config.workspace.minutes_dir / token / "_segs"
            if ctx.dry_run:
                starts = list(range(0, item.duration_seconds, config.transcribe.request_seconds))
                texts = {
                    start: (seg_dir / f"{start:06d}.txt").read_text(encoding="utf-8")
                    for start in starts
                    if (seg_dir / f"{start:06d}.txt").is_file()
                }
                cached_total += len(texts)
                requested_total += len(starts) - len(texts)
                results[token] = _group(
                    texts,
                    item.duration_seconds,
                    config.transcribe.segment_seconds,
                    config.transcribe.request_seconds,
                )
                continue

            seg_dir.mkdir(parents=True, exist_ok=True)
            starts = list(range(0, item.duration_seconds, config.transcribe.request_seconds))
            texts, failures, cached, requested = self._slices(
                path,
                starts,
                seg_dir,
                item,
                provider,
                ffmpeg,
                sleep,
                config.transcribe.request_seconds,
                config.transcribe.concurrency,
                config.transcribe.max_retries,
            )
            cached_total += cached
            requested_total += requested
            if failures:
                failed.append(token)
                updates[token] = ItemState(
                    status="failed",
                    reason=f"{len(failures)} 个切片转写失败",
                )
                continue

            segments = _group(
                texts,
                item.duration_seconds,
                config.transcribe.segment_seconds,
                config.transcribe.request_seconds,
            )
            words = word_count(segments)
            if words < config.preflight.min_words:
                empty.append(token)
                updates[token] = ItemState(
                    status="empty", words=words, reason="转写结果字数低于阈值"
                )
                continue

            results[token] = segments
            updates[token] = ItemState(status="transcribed", words=words)

        if ctx.state is not None and updates and not ctx.dry_run:
            ctx.state.update_items(updates)

        ctx.set("transcript.segments", results, step=self.name, provides=self.provides)
        ctx.logger.info(
            "transcribe: 完成 %d，空 %d，失败 %d；切片缓存命中 %d/%d",
            len(results),
            len(empty),
            len(failed),
            cached_total,
            requested_total,
        )
        return StepResult(
            status="ok",
            outputs={"transcript.segments": results},
            evidence={
                "transcribed": len(results),
                "empty": len(empty),
                "failed": len(failed),
                "cached_slices": cached_total,
                "requested_slices": requested_total,
                "dry_run": ctx.dry_run,
            },
        )

    def _provider(self, ctx: Context) -> AsrProvider:
        name = ctx.config.asr.provider
        provider = ctx.provider(name)
        if isinstance(provider, StepFunAsr):
            provider = provider.with_config(
                api_key=ctx.config.stepfun_api_key,
                model=ctx.config.asr.model,
                timeout=float(ctx.config.transcribe.request_seconds),
            )
        if not isinstance(provider, AsrProvider):
            raise ConfigError(f"provider {name} 未实现 AsrProvider 协议")
        return provider

    def _slices(
        self,
        audio: Path,
        starts: list[int],
        seg_dir: Path,
        item: MinuteRef,
        provider: AsrProvider,
        ffmpeg: str,
        sleep: Callable[[float], None],
        request_seconds: int,
        concurrency: int,
        max_retries: int,
    ) -> tuple[dict[int, str], list[int], int, int]:
        texts: dict[int, str] = {}
        failures: list[int] = []
        cached = 0
        requested = 0

        def one(start: int) -> tuple[int, str | None, bool]:
            cache = seg_dir / f"{start:06d}.txt"
            if cache.is_file():
                return start, cache.read_text(encoding="utf-8"), True

            length = min(request_seconds, item.duration_seconds - start)
            attempts = max(1, max_retries)
            for attempt in range(1, attempts + 1):
                pcm = seg_dir / f"{start:06d}.pcm"
                try:
                    if not extract_pcm(audio, start, length, pcm, ffmpeg=ffmpeg):
                        raise ProviderError("ffmpeg 切片失败")
                    text = provider.transcribe(pcm.read_bytes())
                except ProviderError:
                    if attempt < attempts:
                        sleep(min(0.5 * 2 ** (attempt - 1), 5.0))
                    continue
                finally:
                    pcm.unlink(missing_ok=True)
                cache.write_text(text, encoding="utf-8")
                return start, text, False
            return start, None, False

        with ThreadPoolExecutor(max_workers=max(1, concurrency)) as pool:
            for start, text, was_cached in pool.map(one, starts):
                if was_cached:
                    cached += 1
                else:
                    requested += 1
                if text is None:
                    failures.append(start)
                else:
                    texts[start] = text

        return texts, failures, cached, requested


def _group(
    texts: dict[int, str],
    duration: int,
    segment_seconds: int,
    request_seconds: int,
) -> list[TranscriptSegment]:
    segments: list[TranscriptSegment] = []
    index = 1
    for start in range(0, duration, segment_seconds):
        end = min(start + segment_seconds, duration)
        text = "".join(texts.get(position, "") for position in range(start, end, request_seconds))
        segments.append(TranscriptSegment(index=index, start=start, end=end, text=text.strip()))
        index += 1
    return segments
