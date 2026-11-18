"""Environment diagnostics used by ``fmk doctor``."""

from __future__ import annotations

import os
import shutil
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from fmk.config import Config
from fmk.logging import mask_secret

CheckStatus = Literal["ok", "warn", "fail"]


@dataclass(frozen=True)
class Check:
    name: str
    status: CheckStatus
    detail: str


def _which_or_none(command: str) -> str | None:
    return shutil.which(command)


def _writable(path: Path) -> bool:
    probe = path
    while not probe.exists():
        if probe.parent == probe:
            return False
        probe = probe.parent
    return probe.is_dir() and os.access(probe, os.W_OK)


def run_checks(
    config: Config,
    *,
    which: Callable[[str], str | None] = _which_or_none,
) -> list[Check]:
    """Return one check per dependency, credential and directory."""

    checks: list[Check] = []

    if config.config_path is None:
        checks.append(Check("config", "warn", "未找到 config.toml，使用内置默认值"))
    else:
        checks.append(Check("config", "ok", str(config.config_path)))

    for command in ("lark-cli", "ffmpeg"):
        location = which(command)
        if location:
            checks.append(Check(command, "ok", location))
        else:
            checks.append(Check(command, "fail", f"未在 PATH 中找到 {command}"))

    if config.stepfun_api_key:
        masked = mask_secret(config.stepfun_api_key)
        checks.append(Check("credential", "ok", f"FMK_STEPFUN_API_KEY 已设置（{masked}）"))
    else:
        checks.append(Check("credential", "fail", "未设置 FMK_STEPFUN_API_KEY"))

    for label, path in (
        ("work_dir", config.workspace.work_dir),
        ("minutes_dir", config.workspace.minutes_dir),
        ("state_dir", config.workspace.state_dir),
        ("archive_dir", config.workspace.archive_dir),
    ):
        if _writable(path):
            checks.append(Check(f"workspace.{label}", "ok", str(path)))
        else:
            checks.append(Check(f"workspace.{label}", "fail", f"目录不可写: {path}"))

    return checks


def has_failures(checks: list[Check]) -> bool:
    return any(check.status == "fail" for check in checks)
