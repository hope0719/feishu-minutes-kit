"""Integration tests for the discover and download steps."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from fmk.config import load_config
from fmk.context import Context
from fmk.errors import ProviderError
from fmk.providers.lark_cli import LarkCliProvider
from fmk.state import ItemState, StateStore
from fmk.steps.discover import DiscoverStep
from fmk.steps.download import DownloadStep

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "fake_lark_cli"
TOKEN_A = "aaaaaaaaaaaaaaa1"
TOKEN_B = "bbbbbbbbbbbbbbb2"
TOKEN_C = "ccccccccccccccc3"


def _item(token: str, title: str, start: str) -> dict[str, object]:
    return {
        "token": token,
        "display_info": f"11月17日 · {title}\n关键词：产品，增长",
        "meta_data": {
            "description": f"所有者: YOU 开始时间: {start} 时长: 1 小时 2 分 3 秒",
            "app_link": f"https://example.feishu.cn/minutes/{token}",
        },
    }


def _prepare(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Context, LarkCliProvider]:
    scenario = tmp_path / "fake"
    scenario.mkdir()
    pages = [
        {
            "items": [
                _item(TOKEN_A, "产品周会", "2026.11.17 13:02:34"),
                _item(TOKEN_B, "增长复盘", "2026.11.16 09:00:00"),
            ],
            "has_more": True,
            "page_token": "1",
        },
        {
            "items": [_item(TOKEN_C, "客户访谈", "2026.11.15 20:00:00")],
            "has_more": False,
            "page_token": "",
        },
    ]
    (scenario / "search_pages.json").write_text(json.dumps(pages), encoding="utf-8")
    (scenario / "download.json").write_text(
        json.dumps({TOKEN_A: "a.ogg", TOKEN_B: "b.m4a"}), encoding="utf-8"
    )
    monkeypatch.setenv("FAKE_LARK_DIR", str(scenario))

    config_path = tmp_path / "config.toml"
    config_path.write_text("", encoding="utf-8")
    config = load_config(config_path, env={})
    provider = LarkCliProvider(binary=str(FIXTURE), page_size=2)
    store = StateStore(config.workspace.state_dir / "state.json")
    store.load()
    context = Context(
        config,
        state=store,
        providers={"lark-cli": provider},
        options={"since": "2026-11-10"},
    )
    return context, provider


def test_discover_paginates_sorts_and_dedupes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    context, _ = _prepare(tmp_path, monkeypatch)
    result = DiscoverStep().run(context)

    items = context.require("minutes.list")
    assert [item.token for item in items] == [TOKEN_A, TOKEN_B, TOKEN_C]
    assert result.evidence["fetched"] == 3
    assert result.evidence["new"] == 3
    assert items[0].title == "产品周会"
    assert items[0].duration_seconds == 3723


def test_download_records_no_audio_and_reuses_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    context, _ = _prepare(tmp_path, monkeypatch)
    DiscoverStep().run(context)
    DownloadStep().run(context)

    paths = context.require("audio.path")
    assert set(paths) == {TOKEN_A, TOKEN_B}
    assert all(path.stat().st_size > 0 for path in paths.values())
    assert context.state is not None
    assert context.state.state.items[TOKEN_A].status == "downloaded"
    assert context.state.state.items[TOKEN_C].status == "no-audio"

    calls_path = tmp_path / "fake" / "calls.jsonl"

    def download_calls() -> list[list[str]]:
        return [
            json.loads(line)
            for line in calls_path.read_text(encoding="utf-8").splitlines()
            if "+download" in json.loads(line)
        ]

    first_run_calls = len(download_calls())
    assert first_run_calls == 3

    downloads_only = [
        item for item in context.require("minutes.list") if item.token in {TOKEN_A, TOKEN_B}
    ]
    reuse = Context(
        context.config,
        state=context.state,
        providers=context.providers,
        options={"since": "2026-11-10"},
    )
    reuse.set(
        "minutes.list",
        downloads_only,
        step="discover",
        provides=frozenset({"minutes.list"}),
    )
    DownloadStep().run(reuse)
    assert set(reuse.require("audio.path")) == {TOKEN_A, TOKEN_B}
    assert len(download_calls()) == first_run_calls


def test_known_tokens_are_excluded(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    context, _ = _prepare(tmp_path, monkeypatch)
    archive_day = context.config.workspace.archive_dir / "01-2026-01"
    archive_day.mkdir(parents=True)
    (archive_day / "01-2026-01-01 · 旧稿.md").write_text(
        f"妙记：https://example.feishu.cn/minutes/{TOKEN_B}\n", encoding="utf-8"
    )
    context.state.state.items[TOKEN_C] = ItemState(status="silent")
    context.state.save()

    DiscoverStep().run(context)
    assert [item.token for item in context.require("minutes.list")] == [TOKEN_A]


def test_search_error_is_reported(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    scenario = tmp_path / "fake"
    scenario.mkdir()
    (scenario / "search_pages.json").write_text(
        json.dumps([{"error": "quota exceeded"}]), encoding="utf-8"
    )
    monkeypatch.setenv("FAKE_LARK_DIR", str(scenario))

    provider = LarkCliProvider(binary=str(FIXTURE))
    today = date.today()
    with pytest.raises(ProviderError, match="quota exceeded"):
        provider.search(today, today)


def test_empty_search(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    scenario = tmp_path / "fake"
    scenario.mkdir()
    (scenario / "search_pages.json").write_text("[]", encoding="utf-8")
    monkeypatch.setenv("FAKE_LARK_DIR", str(scenario))

    provider = LarkCliProvider(binary=str(FIXTURE))
    today = date.today()
    assert provider.search(today, today) == []
