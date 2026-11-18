"""Mechanical quote, number and people indexes."""

from __future__ import annotations

import re
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path

from fmk.core.naming import ArchiveItem

SENTENCE_SPLIT = re.compile(r"[。！？!?；;\n]+")
FILLERS = ("嗯", "呃", "啊", "哦", "额", "这个", "那个", "就是")
MARKERS = (
    "因为",
    "所以",
    "但是",
    "其实",
    "本质",
    "关键",
    "核心",
    "记住",
    "一定要",
    "不要",
    "如果",
    "只要",
    "意味着",
    "说明",
    "经验",
    "方法",
    "逻辑",
    "原则",
)
HONORIFIC_RE = re.compile(r"([\u4e00-\u9fa5]{1,2})(老师|老板|总|哥|姐)")
ROLE_STOP = frozenset(
    {
        "老师",
        "老板",
        "同学",
        "朋友",
        "客户",
        "用户",
        "同事",
        "领导",
        "医生",
        "律师",
        "嘉宾",
        "主持",
        "讲师",
        "前辈",
        "大佬",
        "伙伴",
    }
)
MONEY_CATEGORIES: dict[str, re.Pattern[str]] = {
    "报价 / 定价": re.compile(r"报价|定价|客单价|价格"),
    "成本 / 投入": re.compile(r"成本|人工|物料|投入|预算"),
    "收入 / 利润": re.compile(r"营收|收入|利润|流水|回本|毛利"),
    "转化 / 增长": re.compile(r"转化|留存|复购|增长"),
}
QUOTE_MIN, QUOTE_MAX = 16, 48
QUOTE_LIMIT = 80


@dataclass(frozen=True)
class DocBody:
    item: ArchiveItem
    relative: Path
    text: str


@dataclass(frozen=True)
class Hit:
    text: str
    label: str
    link: str


def _documents(items: Sequence[ArchiveItem], archive_dir: Path) -> Iterator[DocBody]:
    for item in items:
        try:
            text = item.path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        _, separator, body = text.partition("\n---\n")
        yield DocBody(
            item=item,
            relative=item.path.relative_to(archive_dir),
            text=body if separator else text,
        )


def _label(item: ArchiveItem) -> str:
    return f"{item.recorded_at.date().isoformat()} · {item.title}"


def _link(item: ArchiveItem, relative: Path) -> str:
    return f"[{_label(item)}]({relative.as_posix()})"


def _sentences(text: str) -> list[str]:
    return [part.strip() for part in SENTENCE_SPLIT.split(text) if part.strip()]


def _is_good_quote(sentence: str) -> bool:
    if not QUOTE_MIN <= len(sentence) <= QUOTE_MAX:
        return False
    if sentence.startswith(("#", "|", ">", "- ")):
        return False
    filler = sum(sentence.count(word) * len(word) for word in FILLERS)
    if filler / len(sentence) > 0.055:
        return False
    if re.search(r"(.)\1{2,}", sentence):
        return False
    return any(marker in sentence for marker in MARKERS)


def _is_number_sentence(sentence: str) -> bool:
    return bool(re.search(r"\d", sentence)) and bool(re.search(r"元|万|千|百|块|%|倍", sentence))


def _people(sentence: str) -> list[str]:
    names: list[str] = []
    for match in HONORIFIC_RE.finditer(sentence):
        prefix, suffix = match.group(1), match.group(2)
        if prefix in ROLE_STOP:
            continue
        names.append(f"{prefix}{suffix}")
    return names


def render_indexes(items: Sequence[ArchiveItem], archive_dir: Path) -> tuple[str, str, str]:
    """Return Markdown for quotes, numbers and people indexes."""

    documents = list(_documents(items, archive_dir))

    quote_lines: list[str] = [
        "# 金句索引",
        "",
        "> 机械抽取，仅作素材线索，需人工复核。",
        "",
    ]
    seen_quotes: set[str] = set()
    quote_count = 0
    for document in documents:
        for sentence in _sentences(document.text):
            if quote_count >= QUOTE_LIMIT:
                break
            if sentence in seen_quotes or not _is_good_quote(sentence):
                continue
            seen_quotes.add(sentence)
            quote_lines.append(f"- “{sentence}” — {_link(document.item, document.relative)}")
            quote_count += 1
    if quote_count == 0:
        quote_lines.append("暂无可用的金句候选。")

    number_sections: dict[str, list[str]] = {key: [] for key in MONEY_CATEGORIES}
    seen_numbers: set[str] = set()
    for document in documents:
        for sentence in _sentences(document.text):
            if sentence in seen_numbers or not _is_number_sentence(sentence):
                continue
            for category, pattern in MONEY_CATEGORIES.items():
                if pattern.search(sentence):
                    seen_numbers.add(sentence)
                    number_sections[category].append(
                        f"- {sentence} — {_link(document.item, document.relative)}"
                    )
                    break

    number_lines: list[str] = [
        "# 数字与金额索引",
        "",
        "> 按关键词机械归类，金额与口径需人工核对。",
        "",
    ]
    for category, lines in number_sections.items():
        number_lines += [f"## {category}", ""]
        number_lines += lines or ["暂无。"]
        number_lines.append("")

    people: dict[str, list[Hit]] = {}
    for document in documents:
        for sentence in _sentences(document.text):
            for name in _people(sentence):
                people.setdefault(name, []).append(
                    Hit(
                        text=name,
                        label=_label(document.item),
                        link=_link(document.item, document.relative),
                    )
                )

    people_lines: list[str] = [
        "# 人名线索",
        "",
        "> 仅按“称呼 + 敬称”机械匹配，可能误判，请人工确认。",
        "",
    ]
    for name in sorted(people):
        sources = []
        seen_links: set[str] = set()
        for hit in people[name]:
            if hit.link in seen_links:
                continue
            seen_links.add(hit.link)
            sources.append(hit.link)
        people_lines.append(f"- **{name}** — " + "；".join(sources[:3]))
    if not people:
        people_lines.append("暂无可用的称呼线索。")

    return (
        "\n".join(quote_lines) + "\n",
        "\n".join(number_lines).rstrip() + "\n",
        "\n".join(people_lines) + "\n",
    )
