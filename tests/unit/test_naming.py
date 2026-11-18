"""Naming, parsing and placement planning."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from fmk.config import load_config
from fmk.core.naming import (
    ArchiveItem,
    parse_document,
    plan_months,
    plan_placements,
    sanitize_title,
)

GOLDEN = Path(__file__).resolve().parents[1] / "fixtures" / "golden" / "single.md"


def _item(token: str, title: str, when: datetime) -> ArchiveItem:
    return ArchiveItem(token=token, path=Path(f"/tmp/{token}.md"), recorded_at=when, title=title)


def _naming(tmp_path: Path, file_format: str | None = None):
    path = tmp_path / "config.toml"
    path.write_text("", encoding="utf-8")
    overrides = {"naming.file_format": file_format} if file_format else None
    return load_config(path, env={}, overrides=overrides).naming


def test_sanitize_title_replaces_unsafe_characters() -> None:
    assert sanitize_title('a/b:c*d?e"f<g>h|i', 80) == "a b c d e f g h i"


def test_sanitize_title_truncates() -> None:
    assert sanitize_title("一二三四五", 3) == "一二三"


def test_months_are_numbered_newest_first(tmp_path: Path) -> None:
    items = [
        _item("a" * 16, "一月", datetime(2026, 1, 5)),
        _item("b" * 16, "二月", datetime(2026, 2, 5)),
    ]
    months = plan_months(items, _naming(tmp_path))
    assert months == {(2026, 2): "01-2026-02", (2026, 1): "02-2026-01"}


def test_placements_follow_date_desc_and_handle_collisions(tmp_path: Path) -> None:
    items = [
        _item("a" * 16, "同名", datetime(2026, 1, 5)),
        _item("b" * 16, "同名", datetime(2026, 1, 5)),
    ]
    naming = _naming(tmp_path, file_format="{date} · {title}.md")
    placements = plan_placements(items, naming)
    names = [placement.file_name for placement in placements]
    assert names[0] == "2026-01-05 · 同名.md"
    assert names[1] == "2026-01-05 · 同名（2）.md"


def test_parse_document_reads_header_fields() -> None:
    parsed = parse_document(
        GOLDEN.read_text(encoding="utf-8"),
        fallback_time=datetime(2020, 1, 1),
    )
    assert parsed.token == "aaaaaaaaaaaaaaa1"
    assert parsed.title == "测试访谈"
    assert parsed.recorded_at == datetime(2026, 11, 17, 13, 2)
    assert parsed.words == 6
    assert parsed.duration_label == "0 分 8 秒"
    assert parsed.source_label == "stepfun stepaudio-2.5-asr 重转"
