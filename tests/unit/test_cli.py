"""CLI smoke tests for init, status, plugins and doctor."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner

from fmk.cli import app, main
from fmk.errors import ConfigError

runner = CliRunner()


def test_init_creates_config_and_workspace(tmp_path: Path) -> None:
    result = runner.invoke(app, ["init", "--dir", str(tmp_path)])
    assert result.exit_code == 0
    assert (tmp_path / "config.toml").is_file()
    assert (tmp_path / ".env.example").is_file()
    assert not (tmp_path / ".env").exists()
    assert (tmp_path / "work" / "minutes").is_dir()
    assert (tmp_path / "archive").is_dir()


def test_init_refuses_overwrite_without_force(tmp_path: Path) -> None:
    runner.invoke(app, ["init", "--dir", str(tmp_path)])
    with pytest.raises(ConfigError, match="已存在"):
        runner.invoke(app, ["init", "--dir", str(tmp_path)], catch_exceptions=False)
    result = runner.invoke(app, ["init", "--dir", str(tmp_path), "--force"])
    assert result.exit_code == 0


def test_plugins_list_shows_builtin_steps() -> None:
    result = runner.invoke(app, ["plugins", "list"])
    assert result.exit_code == 0
    for name in ("discover", "download", "transcribe", "publish"):
        assert name in result.stdout


def test_status_json_reports_pipeline(tmp_path: Path) -> None:
    runner.invoke(app, ["init", "--dir", str(tmp_path)])
    config_path = tmp_path / "config.toml"
    result = runner.invoke(app, ["--config", str(config_path), "status", "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["pipeline"][0] == "discover"
    assert len(payload["pipeline"]) == 9
    assert payload["items"]["total"] == 0


def test_status_plain_text(tmp_path: Path) -> None:
    runner.invoke(app, ["init", "--dir", str(tmp_path)])
    config_path = tmp_path / "config.toml"
    result = runner.invoke(app, ["--config", str(config_path), "status"])
    assert result.exit_code == 0
    assert "流水线" in result.stdout


def test_doctor_prints_checks(tmp_path: Path) -> None:
    runner.invoke(app, ["init", "--dir", str(tmp_path)])
    config_path = tmp_path / "config.toml"
    result = runner.invoke(
        app,
        ["--config", str(config_path), "doctor"],
        env={"FMK_STEPFUN_API_KEY": ""},
    )
    assert "lark-cli" in result.stdout
    assert "credential" in result.stdout


def test_main_maps_config_error_to_exit_2(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["fmk", "init", "--dir", str(tmp_path)])
    with pytest.raises(SystemExit) as first:
        main()
    assert first.value.code == 0

    with pytest.raises(SystemExit) as second:
        main()
    assert second.value.code == 2
