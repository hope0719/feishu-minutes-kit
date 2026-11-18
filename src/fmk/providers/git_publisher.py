"""Publish the archive through git."""

from __future__ import annotations

import subprocess
from pathlib import Path

from fmk.errors import ProviderError
from fmk.logging import redact
from fmk.providers.base import API_VERSION, PublishResult


class GitPublisher:
    """Commit the archive folder and push it to a configured remote."""

    name = "git"
    api_version = API_VERSION

    def __init__(self, git: str = "git", *, timeout: float = 120.0) -> None:
        self.git = git
        self.timeout = timeout

    def _run(self, args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
        try:
            completed = subprocess.run(
                [self.git, "-C", str(cwd), *args],
                capture_output=True,
                text=True,
                timeout=self.timeout,
                check=False,
            )
        except FileNotFoundError as exc:
            raise ProviderError(f"未找到 git: {self.git}") from exc
        except subprocess.TimeoutExpired as exc:
            raise ProviderError(f"git 超时（{self.timeout:g} 秒）") from exc
        if completed.returncode != 0:
            detail = redact(completed.stderr).strip()[:300]
            raise ProviderError(f"git {args[0]} 失败: {detail}")
        return completed

    def _toplevel(self, archive_dir: Path) -> Path:
        result = subprocess.run(
            [self.git, "-C", str(archive_dir), "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            timeout=self.timeout,
            check=False,
        )
        if result.returncode != 0:
            raise ProviderError(
                f"归档目录不在 git 仓库中: {archive_dir}",
                hint="先 git init，或把 workspace.archive_dir 指向已有仓库内的目录",
            )
        return Path(result.stdout.strip())

    def publish(
        self,
        archive_dir: Path,
        *,
        remote: str,
        branch: str,
        message: str,
        dry_run: bool = False,
    ) -> PublishResult:
        root = self._toplevel(archive_dir)
        try:
            relative = archive_dir.resolve().relative_to(root)
        except ValueError:
            relative = Path(".")
        target = relative.as_posix() or "."

        status = self._run(["status", "--porcelain", "--", target], root).stdout
        changed = [line for line in status.splitlines() if line.strip()]
        if not changed:
            return PublishResult(committed=False, commit=None, changed_files=0)
        if dry_run:
            return PublishResult(committed=False, commit=None, changed_files=len(changed))

        self._run(["add", "-A", "--", target], root)
        self._run(["commit", "-m", message, "--", target], root)
        commit = self._run(["rev-parse", "HEAD"], root).stdout.strip()
        self._run(["push", remote, f"HEAD:{branch}"], root)
        return PublishResult(committed=True, commit=commit, changed_files=len(changed))
