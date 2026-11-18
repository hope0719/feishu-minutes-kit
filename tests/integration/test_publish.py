"""Git publishing against local bare repositories."""

from __future__ import annotations

import shutil
import subprocess
from datetime import datetime
from pathlib import Path

import pytest

from fmk.config import load_config
from fmk.context import Context
from fmk.core.markdown import render_document
from fmk.core.transcript import TranscriptSegment
from fmk.errors import ProviderError
from fmk.providers.git_publisher import GitPublisher
from fmk.state import StateStore
from fmk.steps.publish import PublishStep

GIT = shutil.which("git")
pytestmark = pytest.mark.skipif(GIT is None, reason="git is required")
TOKEN = "a" * 16


def _git(*args: str, cwd: Path) -> str:
    completed = subprocess.run(
        [GIT or "git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=True,
    )
    return completed.stdout


def _config(tmp_path: Path, archive: Path, remote: Path, *, enabled: bool = True) -> Path:
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        "[workspace]\n"
        f'archive_dir = "{archive}"\n'
        "[publish]\n"
        f"enabled = {str(enabled).lower()}\n"
        'provider = "git"\n'
        f'remote = "{remote}"\n'
        'branch = "main"\n'
        'commit_message = "chore: sync archive"\n',
        encoding="utf-8",
    )
    return config_path


def _context(config_path: Path) -> Context:
    config = load_config(config_path, env={})
    store = StateStore(config.workspace.state_dir / "state.json")
    store.load()
    context = Context(config, state=store, providers={"git": GitPublisher()})
    context.set("archive.path", {}, step="organize", provides=frozenset({"archive.path"}))
    return context


def _write_doc(archive: Path) -> Path:
    folder = archive / "01-2026-01"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "01-2026-01-05 · 发布测试.md"
    path.write_text(
        render_document(
            title="发布测试",
            start=datetime(2026, 1, 5, 10, 0),
            duration_seconds=60,
            url=f"https://example.feishu.cn/minutes/{TOKEN}",
            asr_label="stepfun stepaudio-2.5-asr",
            segments=[TranscriptSegment(1, 0, 60, "正文")],
        ),
        encoding="utf-8",
    )
    return path


def _repo(tmp_path: Path) -> tuple[Path, Path, Path]:
    remote = tmp_path / "remote.git"
    _git("init", "--bare", str(remote), cwd=tmp_path)
    repo = tmp_path / "repo"
    repo.mkdir()
    _git("init", cwd=repo)
    _git("config", "user.email", "test@example.com", cwd=repo)
    _git("config", "user.name", "Test", cwd=repo)
    archive = repo / "archive"
    archive.mkdir()
    return repo, archive, remote


def test_publish_commits_and_pushes(tmp_path: Path) -> None:
    _, archive, remote = _repo(tmp_path)
    doc = _write_doc(archive)
    context = _context(_config(tmp_path, archive, remote))

    result = PublishStep().run(context)
    assert result.evidence["committed"] is True
    assert result.evidence["commit"]
    assert result.evidence["changed_files"] == 1

    log = _git("--git-dir", str(remote), "log", "--oneline", "main", cwd=tmp_path)
    assert len(log.strip().splitlines()) == 1
    assert context.state is not None
    assert context.state.state.items[TOKEN].status == "published"

    doc.write_text(doc.read_text(encoding="utf-8") + "\n补充\n", encoding="utf-8")
    second = PublishStep().run(context)
    assert second.evidence["committed"] is True
    assert second.evidence["changed_files"] == 1


def test_publish_without_changes_skips_commit(tmp_path: Path) -> None:
    _, archive, remote = _repo(tmp_path)
    _write_doc(archive)
    context = _context(_config(tmp_path, archive, remote))
    PublishStep().run(context)

    again = PublishStep().run(_context(_config(tmp_path, archive, remote)))
    assert again.evidence["committed"] is False
    assert again.evidence["changed_files"] == 0
    log = _git("--git-dir", str(remote), "log", "--oneline", "main", cwd=tmp_path)
    assert len(log.strip().splitlines()) == 1


def test_dry_run_does_not_commit(tmp_path: Path) -> None:
    _, archive, remote = _repo(tmp_path)
    doc = _write_doc(archive)
    context = _context(_config(tmp_path, archive, remote))
    PublishStep().run(context)

    doc.write_text(doc.read_text(encoding="utf-8") + "\n再补充\n", encoding="utf-8")
    dry = _context(_config(tmp_path, archive, remote))
    dry.dry_run = True
    result = PublishStep().run(dry)

    assert result.evidence["committed"] is False
    assert result.evidence["changed_files"] == 1
    log = _git("--git-dir", str(remote), "log", "--oneline", "main", cwd=tmp_path)
    assert len(log.strip().splitlines()) == 1
    status = _git("status", "--porcelain", cwd=tmp_path / "repo")
    assert "archive/" in status


def test_disabled_publish_is_skipped(tmp_path: Path) -> None:
    archive = tmp_path / "archive"
    archive.mkdir()
    remote = tmp_path / "remote.git"
    context = _context(_config(tmp_path, archive, remote, enabled=False))
    result = PublishStep().run(context)
    assert result.status == "skip"
    assert context.require("publish.result")["skipped"] is True


def test_non_repo_archive_raises(tmp_path: Path) -> None:
    archive = tmp_path / "archive"
    archive.mkdir()
    remote = tmp_path / "remote.git"
    context = _context(_config(tmp_path, archive, remote))
    with pytest.raises(ProviderError, match="git 仓库"):
        PublishStep().run(context)
