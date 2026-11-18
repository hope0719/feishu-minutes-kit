"""Minutes provider backed by the external ``lark-cli`` executable."""

from __future__ import annotations

import html
import json
import re
import shutil
import subprocess
from datetime import date, datetime
from pathlib import Path
from typing import Any

from fmk.core.audio import find_audio
from fmk.errors import ProviderError
from fmk.logging import get_logger, redact
from fmk.providers.base import API_VERSION, MinuteMeta, MinuteRef

_START_RE = re.compile(r"开始时间[:：]\s*(\d{4})\.(\d{2})\.(\d{2})\s+(\d{2}):(\d{2}):(\d{2})")
_DURATION_RE = re.compile(r"时长[:：]\s*(?:(\d+)\s*小时)?\s*(?:(\d+)\s*分)?\s*(?:(\d+)\s*秒)?")
_DATE_PREFIX_RE = re.compile(r"^\d{1,2}月\d{1,2}日\s*·\s*")
_KEYWORDS_RE = re.compile(r"关键词[:：]\s*(.+?)(?:\n|$)")


def parse_description(text: str) -> tuple[datetime | None, int]:
    """Parse the description field of a search hit.

    Example input: ``所有者: … 开始时间: 2026.11.17 13:02:34 时长: 5 小时 33 分 11 秒``.
    """

    match = _START_RE.search(text)
    start: datetime | None = None
    if match:
        year, month, day, hour, minute, second = (int(part) for part in match.groups())
        start = datetime(year, month, day, hour, minute, second)
    duration_match = _DURATION_RE.search(text)
    duration = 0
    if duration_match:
        hours, minutes, seconds = (int(part or 0) for part in duration_match.groups())
        duration = hours * 3600 + minutes * 60 + seconds
    return start, duration


def parse_display(display_info: str) -> tuple[str, tuple[str, ...]]:
    """Extract a clean title and keywords from ``display_info``."""

    decoded = html.unescape(display_info)
    first_line = decoded.split("\n")[0].strip()
    title = _DATE_PREFIX_RE.sub("", first_line).strip() or "未命名"
    keywords: tuple[str, ...] = ()
    match = _KEYWORDS_RE.search(decoded)
    if match:
        parts = [part.strip() for part in re.split(r"[，,、]", match.group(1))]
        keywords = tuple(part for part in parts if part)[:12]
    return title, keywords


class LarkCliProvider:
    """Call ``lark-cli minutes`` and normalise its JSON output."""

    name = "lark-cli"
    api_version = API_VERSION

    def __init__(
        self,
        binary: str | None = None,
        *,
        timeout: float = 120.0,
        page_size: int = 30,
        max_pages: int = 100,
    ) -> None:
        self._binary = binary
        self.timeout = timeout
        self.page_size = page_size
        self.max_pages = max_pages
        self.logger = get_logger()

    @property
    def binary(self) -> str:
        if self._binary:
            return self._binary
        found = shutil.which("lark-cli")
        if found is None:
            raise ProviderError(
                "未找到 lark-cli",
                hint="请安装 lark-cli 并确保它在 PATH 中，可用 fmk doctor 检查",
            )
        self._binary = found
        return found

    def _call(self, args: list[str]) -> dict[str, Any]:
        command = [self.binary, "minutes", *args, "--json"]
        try:
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=self.timeout,
                check=False,
            )
        except FileNotFoundError as exc:
            raise ProviderError(f"无法执行 {self.binary}") from exc
        except subprocess.TimeoutExpired as exc:
            raise ProviderError(f"lark-cli 超时（{self.timeout:g} 秒）") from exc

        output = completed.stdout
        index = output.find("{")
        if index < 0:
            detail = redact(completed.stderr).strip()[:300]
            raise ProviderError(f"lark-cli 无 JSON 输出: {detail}")
        try:
            data = json.loads(output[index:])
        except json.JSONDecodeError as exc:
            raise ProviderError("lark-cli 输出了非法 JSON") from exc
        if not isinstance(data, dict):
            raise ProviderError("lark-cli 输出不是 JSON 对象")
        if not data.get("ok"):
            raise ProviderError(f"lark-cli 调用失败: {redact(str(data.get('error')))}")
        payload = data.get("data")
        return payload if isinstance(payload, dict) else {}

    def search(self, start: date, end: date) -> list[MinuteRef]:
        items: list[MinuteRef] = []
        seen: set[str] = set()
        page_token = ""

        for _ in range(self.max_pages):
            args = [
                "+search",
                "--start",
                start.isoformat(),
                "--end",
                end.isoformat(),
                "--page-size",
                str(self.page_size),
            ]
            if page_token:
                args.extend(["--page-token", page_token])
            data = self._call(args)

            raw_items = data.get("items") or []
            if not isinstance(raw_items, list):
                raise ProviderError("lark-cli 搜索结果的 items 不是列表")
            for raw in raw_items:
                ref = self._parse_item(raw)
                if ref is not None and ref.token not in seen:
                    seen.add(ref.token)
                    items.append(ref)

            if len(raw_items) >= self.page_size and not data.get("has_more"):
                self.logger.warning("搜索结果达到单页上限且 has_more=false，可能漏扫")

            next_token = data.get("page_token") or ""
            if not data.get("has_more") or not next_token:
                break
            page_token = str(next_token)
        else:
            raise ProviderError(
                f"lark-cli 分页超过 {self.max_pages} 页，已中止",
                hint="缩小 --since 日期窗口后重试",
            )

        items.sort(key=lambda ref: ref.start or datetime.min, reverse=True)
        return items

    def _parse_item(self, raw: Any) -> MinuteRef | None:
        if not isinstance(raw, dict):
            return None
        token = raw.get("token")
        if not isinstance(token, str) or not token:
            return None

        display = raw.get("display_info")
        display_text = display if isinstance(display, str) else ""
        title, keywords = parse_display(display_text)

        meta = raw.get("meta_data")
        meta_data = meta if isinstance(meta, dict) else {}
        description = meta_data.get("description")
        start, duration = parse_description(description if isinstance(description, str) else "")
        url = meta_data.get("app_link")
        return MinuteRef(
            token=token,
            title=title,
            start=start,
            duration_seconds=duration,
            url=url if isinstance(url, str) else "",
            keywords=keywords,
        )

    def meta(self, token: str) -> MinuteMeta:
        data = self._call(["minutes", "get", "--minute-token", token])
        minute = data.get("minute")
        if not isinstance(minute, dict):
            raise ProviderError(f"lark-cli 未返回妙记元数据: {token}")

        start: datetime | None = None
        raw_create = minute.get("create_time")
        if raw_create is not None:
            try:
                start = datetime.fromtimestamp(int(raw_create) / 1000)
            except (TypeError, ValueError, OSError):
                start = None
        duration_ms = minute.get("duration", 0)
        try:
            duration = int(duration_ms) // 1000
        except (TypeError, ValueError):
            duration = 0
        title = minute.get("title")
        url = minute.get("url")
        return MinuteMeta(
            token=token,
            title=str(title) if title else "未命名",
            start=start,
            duration_seconds=duration,
            url=str(url) if url else "",
        )

    def download(self, token: str, dest: Path) -> Path | None:
        existing = find_audio(dest)
        if existing is not None:
            return existing
        dest.mkdir(parents=True, exist_ok=True)
        self._call(
            ["+download", "--minute-tokens", token, "--output-dir", str(dest), "--overwrite"]
        )
        return find_audio(dest)

    def official_transcript(self, token: str) -> str | None:
        """Not used in v0.1; reserved for cross-checking official transcripts."""

        return None
