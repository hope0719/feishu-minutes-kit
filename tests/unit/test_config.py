"""Configuration precedence and validation."""

from __future__ import annotations

from pathlib import Path

import pytest

from fmk.config import load_config
from fmk.errors import ConfigError


def _write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "config.toml"
    path.write_text(text, encoding="utf-8")
    return path


def test_defaults_when_no_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    config = load_config(env={})
    assert config.config_path is None
    assert config.workspace.work_dir == (tmp_path / "work").resolve()
    assert config.workspace.archive_dir == (tmp_path / "archive").resolve()
    assert config.naming.max_title_chars == 80
    assert config.pipeline.steps[0] == "discover"
    assert len(config.pipeline.steps) == 9
    assert config.stepfun_api_key is None


def test_toml_overrides_defaults(tmp_path: Path) -> None:
    path = _write(tmp_path, "[naming]\nmax_title_chars = 60\n")
    config = load_config(path, env={})
    assert config.naming.max_title_chars == 60
    assert config.workspace.work_dir == (tmp_path / "work").resolve()


def test_cli_overrides_toml(tmp_path: Path) -> None:
    path = _write(tmp_path, "[naming]\nmax_title_chars = 60\n")
    config = load_config(path, env={}, overrides={"naming.max_title_chars": 40})
    assert config.naming.max_title_chars == 40


def test_env_supplies_credential(tmp_path: Path) -> None:
    path = _write(tmp_path, "")
    config = load_config(path, env={"FMK_STEPFUN_API_KEY": "test-key-abcd"})
    assert config.stepfun_api_key == "test-key-abcd"


def test_relative_paths_resolve_against_config_dir(tmp_path: Path) -> None:
    nested = tmp_path / "project"
    nested.mkdir()
    path = nested / "config.toml"
    path.write_text('[workspace]\narchive_dir = "./out"\n', encoding="utf-8")
    config = load_config(path, env={})
    assert config.workspace.archive_dir == (nested / "out").resolve()


def test_invalid_integer_reports_key(tmp_path: Path) -> None:
    path = _write(tmp_path, "[transcribe]\nconcurrency = 0\n")
    with pytest.raises(ConfigError, match="transcribe.concurrency"):
        load_config(path, env={})


def test_publish_requires_remote(tmp_path: Path) -> None:
    path = _write(tmp_path, '[publish]\nenabled = true\nremote = ""\n')
    with pytest.raises(ConfigError, match="publish.remote"):
        load_config(path, env={})


def test_invalid_toml(tmp_path: Path) -> None:
    path = _write(tmp_path, "not valid = = toml\n")
    with pytest.raises(ConfigError, match="不是合法 TOML"):
        load_config(path, env={})


def test_missing_file(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="配置文件不存在"):
        load_config(tmp_path / "nope.toml", env={})


def test_invalid_format_template(tmp_path: Path) -> None:
    path = _write(tmp_path, '[naming]\ndir_format = "{unknown}"\n')
    with pytest.raises(ConfigError, match="naming.dir_format"):
        load_config(path, env={})


def test_duplicate_pipeline_steps(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        '[pipeline]\nsteps = ["discover", "discover"]\n',
    )
    with pytest.raises(ConfigError, match="重复步骤"):
        load_config(path, env={})
