"""Environment diagnostics."""

from __future__ import annotations

from pathlib import Path

from fmk.config import Config, load_config
from fmk.doctor import has_failures, run_checks


def _config(tmp_path: Path, *, key: str | None = None) -> Config:
    path = tmp_path / "config.toml"
    path.write_text("", encoding="utf-8")
    env = {"FMK_STEPFUN_API_KEY": key} if key else {}
    return load_config(path, env=env)


def test_missing_commands_and_credential_fail(tmp_path: Path) -> None:
    config = _config(tmp_path)
    checks = run_checks(config, which=lambda command: None)
    by_name = {check.name: check for check in checks}

    assert by_name["lark-cli"].status == "fail"
    assert by_name["ffmpeg"].status == "fail"
    assert by_name["credential"].status == "fail"
    assert by_name["workspace.work_dir"].status == "ok"
    assert has_failures(checks)


def test_present_commands_and_masked_credential(tmp_path: Path) -> None:
    config = _config(tmp_path, key="abcd1234")
    checks = run_checks(config, which=lambda command: f"/usr/bin/{command}")
    by_name = {check.name: check for check in checks}

    assert by_name["lark-cli"].status == "ok"
    assert by_name["ffmpeg"].status == "ok"
    assert by_name["credential"].status == "ok"
    assert "abcd****" in by_name["credential"].detail
    assert "abcd1234" not in by_name["credential"].detail
    assert not has_failures(checks)
