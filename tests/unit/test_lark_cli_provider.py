"""Parsing helpers and error paths of the lark-cli provider."""

from __future__ import annotations

from datetime import datetime

import pytest

from fmk.errors import ProviderError
from fmk.providers.lark_cli import LarkCliProvider, parse_description, parse_display


def test_parse_description_with_duration() -> None:
    text = "所有者: YOU 开始时间: 2026.11.17 13:02:34 时长: 5 小时 33 分 11 秒"
    start, duration = parse_description(text)
    assert start == datetime(2026, 11, 17, 13, 2, 34)
    assert duration == 5 * 3600 + 33 * 60 + 11


def test_parse_description_without_fields() -> None:
    assert parse_description("没有可用信息") == (None, 0)


def test_parse_display_strips_date_prefix_and_reads_keywords() -> None:
    display = "11月17日 · 产品周会\n关键词：产品，增长、复盘"
    title, keywords = parse_display(display)
    assert title == "产品周会"
    assert keywords == ("产品", "增长", "复盘")


def test_parse_display_falls_back_to_unnamed() -> None:
    title, keywords = parse_display("\n")
    assert title == "未命名"
    assert keywords == ()


def test_missing_binary_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("fmk.providers.lark_cli.shutil.which", lambda command: None)
    provider = LarkCliProvider()
    with pytest.raises(ProviderError, match="lark-cli"):
        provider.search(datetime.now().date(), datetime.now().date())
