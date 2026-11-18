"""Archive organisation, navigation, queue and idempotency."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from fmk.config import load_config
from fmk.context import Context
from fmk.core.markdown import render_document
from fmk.core.transcript import TranscriptSegment
from fmk.state import ItemState, StateStore
from fmk.steps.index import IndexStep
from fmk.steps.organize import OrganizeStep
from fmk.steps.reconcile import ReconcileStep

TOKEN_A = "a" * 16
TOKEN_B = "b" * 16
TOKEN_C = "c" * 16
BODY = (
    "其实核心逻辑很简单，先把报价定在 199 元，转化率才有保障。"
    "张老师说这个方案要记住，客户体验才是关键。"
)


def _context(tmp_path: Path, docs: dict[str, Path], *, index: bool = True) -> Context:
    config_path = tmp_path / "config.toml"
    config_path.write_text(f"[index]\nenabled = {str(index).lower()}\n", encoding="utf-8")
    config = load_config(config_path, env={})
    store = StateStore(config.workspace.state_dir / "state.json")
    store.load()
    context = Context(config, state=store)
    context.set("doc.path", docs, step="compose", provides=frozenset({"doc.path"}))
    return context


def _compose(context: Context, token: str, title: str, when: datetime, text: str = BODY) -> Path:
    path = context.config.workspace.work_dir / "docs" / f"{token}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        render_document(
            title=title,
            start=when,
            duration_seconds=1800,
            url=f"https://example.feishu.cn/minutes/{token}",
            asr_label="stepfun stepaudio-2.5-asr",
            segments=[TranscriptSegment(1, 0, 1800, text)],
        ),
        encoding="utf-8",
    )
    return path


def _run_all(context: Context) -> None:
    OrganizeStep().run(context)
    ReconcileStep().run(context)
    IndexStep().run(context)


def _snapshot(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): path.read_text(encoding="utf-8")
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def test_archive_layout_navigation_and_indexes(tmp_path: Path) -> None:
    context = _context(
        tmp_path,
        {
            TOKEN_A: Path(),
            TOKEN_B: Path(),
        },
    )
    docs = {
        TOKEN_A: _compose(context, TOKEN_A, "一月访谈", datetime(2026, 1, 5, 10, 0)),
        TOKEN_B: _compose(context, TOKEN_B, "一月复盘", datetime(2026, 1, 10, 9, 0)),
    }
    context.set("doc.path", docs, step="compose", provides=frozenset({"doc.path"}))
    _run_all(context)

    archive = context.config.workspace.archive_dir
    month = archive / "01-2026-01"
    assert month.is_dir()
    assert (month / "01-2026-01-10 · 一月复盘.md").is_file()
    assert (month / "02-2026-01-05 · 一月访谈.md").is_file()
    assert (month / "_index.md").is_file()
    assert (archive / "_overview.md").is_file()
    assert (archive / "_queue.md").is_file()
    assert (archive / "_queue-history.md").is_file()

    overview = (archive / "_overview.md").read_text(encoding="utf-8")
    assert "一月复盘" in overview and "一月访谈" in overview
    month_index = (month / "_index.md").read_text(encoding="utf-8")
    assert "01-2026-01-10 · 一月复盘.md" in month_index

    quotes = (archive / "_quotes.md").read_text(encoding="utf-8")
    numbers = (archive / "_numbers.md").read_text(encoding="utf-8")
    people = (archive / "_people.md").read_text(encoding="utf-8")
    assert "其实核心逻辑" in quotes
    assert "199" in numbers and "报价 / 定价" in numbers
    assert "**张老师**" in people

    assert context.state is not None
    assert context.state.state.items[TOKEN_A].status == "organized"


def test_reorganize_is_idempotent(tmp_path: Path) -> None:
    context = _context(tmp_path, {TOKEN_A: Path()})
    docs = {TOKEN_A: _compose(context, TOKEN_A, "稳定输出", datetime(2026, 1, 5, 10, 0))}
    context.set("doc.path", docs, step="compose", provides=frozenset({"doc.path"}))
    _run_all(context)

    archive = context.config.workspace.archive_dir
    first = _snapshot(archive)

    again = _context(tmp_path, {})
    _run_all(again)
    assert _snapshot(archive) == first


def test_new_month_renumbers_existing_archive(tmp_path: Path) -> None:
    context = _context(tmp_path, {TOKEN_A: Path()})
    docs = {TOKEN_A: _compose(context, TOKEN_A, "一月访谈", datetime(2026, 1, 5, 10, 0))}
    context.set("doc.path", docs, step="compose", provides=frozenset({"doc.path"}))
    OrganizeStep().run(context)

    archive = context.config.workspace.archive_dir
    assert (archive / "01-2026-01" / "01-2026-01-05 · 一月访谈.md").is_file()

    second = _context(tmp_path, {TOKEN_B: Path()})
    new_doc = _compose(second, TOKEN_B, "二月复盘", datetime(2026, 2, 1, 10, 0))
    second.set("doc.path", {TOKEN_B: new_doc}, step="compose", provides=frozenset({"doc.path"}))
    OrganizeStep().run(second)

    assert not (archive / "01-2026-01").exists()
    assert (archive / "01-2026-02" / "01-2026-02-01 · 二月复盘.md").is_file()
    assert (archive / "02-2026-01" / "01-2026-01-05 · 一月访谈.md").is_file()


def test_queue_reports_pending_orphans_and_duplicates(tmp_path: Path) -> None:
    context = _context(tmp_path, {})
    archive = context.config.workspace.archive_dir
    duplicate = "d" * 16
    for folder, title, when in (
        ("01-2026-01", "重复甲", datetime(2026, 1, 5, 10, 0)),
        ("01-2026-02", "重复乙", datetime(2026, 2, 5, 10, 0)),
    ):
        target = archive / folder
        target.mkdir(parents=True)
        (target / f"{title}.md").write_text(
            render_document(
                title=title,
                start=when,
                duration_seconds=60,
                url=f"https://example.feishu.cn/minutes/{duplicate}",
                asr_label="stepfun stepaudio-2.5-asr",
                segments=[TranscriptSegment(1, 0, 60, "正文")],
            ),
            encoding="utf-8",
        )

    pending = "p" * 16
    orphan = "o" * 16
    minutes = context.config.workspace.minutes_dir
    for token in (pending, orphan):
        folder = minutes / token
        folder.mkdir(parents=True)
        (folder / "audio.ogg").write_bytes(b"audio")
    assert context.state is not None
    context.state.update_item(pending, ItemState(status="downloaded"))

    queue_path = archive / "_queue.md"
    queue_path.write_text(
        "手工备注\n<!-- fmk:status:start -->\n旧内容\n<!-- fmk:status:end -->\n尾部\n",
        encoding="utf-8",
    )

    context.set("archive.path", {}, step="organize", provides=frozenset({"archive.path"}))
    result = ReconcileStep().run(context)
    status = context.require("queue.status")

    assert status["pending"] == 1
    assert status["with_audio"] == 1
    assert status["orphan_audio"] == 2
    assert status["duplicates"] == [duplicate]
    assert result.evidence["total_docs"] == 2

    text = queue_path.read_text(encoding="utf-8")
    assert text.startswith("手工备注")
    assert text.rstrip().endswith("尾部")
    assert "重复发布告警" in text
    assert pending in text


def test_index_disabled_returns_skip(tmp_path: Path) -> None:
    context = _context(tmp_path, {}, index=False)
    context.set("archive.path", {}, step="organize", provides=frozenset({"archive.path"}))
    result = IndexStep().run(context)
    assert result.status == "skip"
    assert context.require("index.files") == {}
