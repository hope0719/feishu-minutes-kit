"""Organise composed documents into a numbered monthly archive."""

from __future__ import annotations

import contextlib
import os
from datetime import datetime
from pathlib import Path

from fmk.context import Context
from fmk.core.naming import (
    MONTH_DIR_RE,
    ArchiveItem,
    Placement,
    ensure_unique_tokens,
    parse_document,
    plan_months,
    plan_placements,
    scan_archive,
)
from fmk.core.navigation import NavEntry, write_navigation
from fmk.errors import VerificationError
from fmk.providers.base import API_VERSION
from fmk.state import ItemState
from fmk.steps.base import StepResult


class OrganizeStep:
    """Renumber months and files so the archive stays continuous."""

    api_version = API_VERSION
    name = "organize"
    requires: frozenset[str] = frozenset({"doc.path"})
    provides: frozenset[str] = frozenset({"archive.path"})

    def run(self, ctx: Context) -> StepResult:
        docs: dict[str, Path] = dict(ctx.require("doc.path"))
        archive = ctx.config.workspace.archive_dir
        naming = ctx.config.naming
        existing = scan_archive(archive)
        ensure_unique_tokens(existing)
        by_token = {item.token: item for item in existing}

        merged: dict[str, ArchiveItem] = {}
        stale: list[Path] = []
        for item in existing:
            merged[item.token] = item

        for token, path in docs.items():
            if not path.is_file():
                if token in by_token:
                    continue
                ctx.logger.warning("organize: 成稿不存在，已跳过 %s", path)
                continue
            parsed = parse_document(
                path.read_text(encoding="utf-8", errors="ignore"),
                fallback_time=datetime.fromtimestamp(path.stat().st_mtime),
            )
            if parsed.token is not None and parsed.token != token:
                raise VerificationError(f"成稿 {path} 中的妙记 token 与文件名不一致")
            previous = by_token.get(token)
            if previous is not None:
                stale.append(previous.path)
            merged[token] = ArchiveItem(
                token=token,
                path=path,
                recorded_at=parsed.recorded_at,
                title=parsed.title or token,
                words=parsed.words,
                duration_label=parsed.duration_label,
                source_label=parsed.source_label,
            )

        items = list(merged.values())
        placements = plan_placements(items, naming)
        months = plan_months(items, naming)

        if ctx.dry_run:
            paths = {
                placement.item.token: archive / placement.month_dir / placement.file_name
                for placement in placements
            }
            ctx.set("archive.path", paths, step=self.name, provides=self.provides)
            return StepResult(
                status="ok",
                outputs={"archive.path": paths},
                evidence={"items": len(paths), "dry_run": True},
            )

        renamed = self._rename_months(archive, months)
        self._apply_renames(archive, renamed)
        if renamed:
            for placement in placements:
                placement.item.path = _rebase(placement.item.path, renamed)
            stale = [_rebase(path, renamed) for path in stale]

        placements, moved = self._move_files(archive, placements, stale)

        entries = [
            NavEntry(
                item=placement.item,
                path=archive / placement.month_dir / placement.file_name,
                month_dir=placement.month_dir,
            )
            for placement in placements
        ]
        write_navigation(archive, entries)

        paths = {entry.item.token: entry.path for entry in entries}
        updates = {
            placement.item.token: ItemState(
                status="organized",
                words=placement.item.words,
                files=[str(Path(placement.month_dir) / placement.file_name)],
            )
            for placement in placements
        }
        if ctx.state is not None and updates:
            ctx.state.update_items(updates)

        ctx.set("archive.path", paths, step=self.name, provides=self.provides)
        ctx.logger.info("organize: 归档 %d 篇，移动 %d 个文件", len(entries), moved)
        return StepResult(
            status="ok",
            outputs={"archive.path": paths},
            evidence={
                "items": len(entries),
                "moved": moved,
                "months": len(months),
                "renamed_months": len(renamed),
            },
        )

    def _rename_months(self, archive: Path, months: dict[tuple[int, int], str]) -> dict[Path, Path]:
        if not archive.is_dir():
            return {}
        candidates: list[tuple[Path, Path]] = []
        sources: set[Path] = set()
        for folder in sorted(archive.iterdir()):
            match = MONTH_DIR_RE.match(folder.name)
            if not (folder.is_dir() and match):
                continue
            target = months.get((int(match.group(1)), int(match.group(2))))
            if target is None or target == folder.name:
                continue
            candidates.append((folder, archive / target))
            sources.add(folder)

        mapping: dict[Path, Path] = {}
        for folder, destination in candidates:
            if destination.exists() and destination not in sources:
                raise VerificationError(f"月份目录冲突，拒绝覆盖: {destination}")
            mapping[folder] = destination
        return mapping

    def _apply_renames(self, archive: Path, mapping: dict[Path, Path]) -> None:
        if not mapping:
            return
        staged: list[tuple[Path, Path]] = []
        for index, (source, destination) in enumerate(mapping.items()):
            temp = archive / f".fmk-month-{index}.tmp"
            os.replace(source, temp)
            staged.append((temp, destination))
        for temp, destination in staged:
            os.replace(temp, destination)

    def _move_files(
        self, archive: Path, placements: list[Placement], stale: list[Path]
    ) -> tuple[list[Placement], int]:
        managed = {placement.item.path for placement in placements}
        allowed = managed | set(stale)

        for placement in placements:
            final = archive / placement.month_dir / placement.file_name
            if final.exists() and final not in allowed:
                raise VerificationError(f"目标文件已存在，拒绝覆盖: {final}")

        moves: list[tuple[Path, Path]] = []
        moved = 0
        for index, placement in enumerate(placements):
            target_dir = archive / placement.month_dir
            target_dir.mkdir(parents=True, exist_ok=True)
            source = placement.item.path
            final = target_dir / placement.file_name
            if source == final:
                continue
            temp = target_dir / f".fmk-file-{index}.tmp"
            os.replace(source, temp)
            moves.append((temp, final))
            moved += 1

        for temp, final in moves:
            os.replace(temp, final)

        final_targets = {
            archive / placement.month_dir / placement.file_name for placement in placements
        }
        for path in stale:
            if path in managed or path in final_targets:
                continue
            with contextlib.suppress(FileNotFoundError):
                path.unlink()
        return placements, moved


def _rebase(path: Path, mapping: dict[Path, Path]) -> Path:
    parent = mapping.get(path.parent)
    return parent / path.name if parent is not None else path
