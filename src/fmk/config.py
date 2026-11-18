"""Configuration loading with defaults < TOML < environment < CLI precedence."""

from __future__ import annotations

import os
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover - Python 3.10 fallback
    import tomli as tomllib  # type: ignore[import-not-found]

from fmk.errors import ConfigError

CONFIG_FILENAME = "config.toml"
ENV_CONFIG_PATH = "FMK_CONFIG"
ENV_API_KEY = "FMK_STEPFUN_API_KEY"

DEFAULT_SETTINGS: dict[str, Any] = {
    "workspace.work_dir": "./work",
    "workspace.minutes_dir": "./work/minutes",
    "workspace.state_dir": "./work/state",
    "workspace.archive_dir": "./archive",
    "naming.dir_format": "{index:02d}-{year}-{month:02d}",
    "naming.file_format": "{index:02d}-{date} · {title}.md",
    "naming.max_title_chars": 80,
    "preflight.silent_db": -50.0,
    "preflight.min_words": 20,
    "transcribe.segment_seconds": 1500,
    "transcribe.request_seconds": 120,
    "transcribe.concurrency": 3,
    "transcribe.max_retries": 3,
    "source.provider": "lark-cli",
    "asr.provider": "stepfun",
    "asr.model": "stepaudio-2.5-asr",
    "index.enabled": False,
    "publish.enabled": False,
    "publish.provider": "git",
    "publish.remote": "",
    "publish.branch": "main",
    "publish.commit_message": "chore: sync minutes archive",
    "pipeline.steps": [
        "discover",
        "download",
        "preflight",
        "transcribe",
        "compose",
        "organize",
        "reconcile",
        "index",
        "publish",
    ],
}

DEFAULT_CONFIG_TOML = """\
# feishu-minutes-kit 配置，由 `fmk init` 生成。
# 本文件已被 .gitignore 忽略，请勿提交真实凭证或个人信息。

[workspace]
work_dir = "./work"
minutes_dir = "./work/minutes"
state_dir = "./work/state"
archive_dir = "./archive"

[naming]
dir_format = "{index:02d}-{year}-{month:02d}"
file_format = "{index:02d}-{date} · {title}.md"
max_title_chars = 80

[preflight]
silent_db = -50.0
min_words = 20

[transcribe]
segment_seconds = 1500
request_seconds = 120
concurrency = 3
max_retries = 3

[source]
provider = "lark-cli"

[asr]
provider = "stepfun"
model = "stepaudio-2.5-asr"

[index]
enabled = false

[publish]
enabled = false
provider = "git"
remote = ""
branch = "main"
commit_message = "chore: sync minutes archive"

[pipeline]
steps = [
  "discover", "download", "preflight", "transcribe", "compose",
  "organize", "reconcile", "index", "publish",
]
"""

ENV_EXAMPLE = """\
# 复制为 .env 后填入自己的凭证；该文件已被 .gitignore 忽略。
# 工具不会自动读取 .env：请在 shell 中 export，或运行 `set -a; source .env; set +a`。
FMK_STEPFUN_API_KEY=
"""


@dataclass(frozen=True)
class WorkspaceConfig:
    root: Path
    work_dir: Path
    minutes_dir: Path
    state_dir: Path
    archive_dir: Path


@dataclass(frozen=True)
class NamingConfig:
    dir_format: str
    file_format: str
    max_title_chars: int


@dataclass(frozen=True)
class PreflightConfig:
    silent_db: float
    min_words: int


@dataclass(frozen=True)
class TranscribeConfig:
    segment_seconds: int
    request_seconds: int
    concurrency: int
    max_retries: int


@dataclass(frozen=True)
class SourceConfig:
    provider: str


@dataclass(frozen=True)
class AsrConfig:
    provider: str
    model: str


@dataclass(frozen=True)
class IndexConfig:
    enabled: bool


@dataclass(frozen=True)
class PublishConfig:
    enabled: bool
    provider: str
    remote: str
    branch: str
    commit_message: str


@dataclass(frozen=True)
class PipelineConfig:
    steps: tuple[str, ...]


@dataclass(frozen=True)
class Config:
    workspace: WorkspaceConfig
    naming: NamingConfig
    preflight: PreflightConfig
    transcribe: TranscribeConfig
    source: SourceConfig
    asr: AsrConfig
    index: IndexConfig
    publish: PublishConfig
    pipeline: PipelineConfig
    stepfun_api_key: str | None = None
    config_path: Path | None = None

    def ensure_directories(self) -> None:
        """Create the workspace directories if they do not exist yet."""

        for path in (
            self.workspace.work_dir,
            self.workspace.minutes_dir,
            self.workspace.state_dir,
            self.workspace.archive_dir,
        ):
            path.mkdir(parents=True, exist_ok=True)


def _flatten(data: Mapping[str, Any], prefix: str = "") -> dict[str, Any]:
    flat: dict[str, Any] = {}
    for key, value in data.items():
        if not isinstance(key, str):
            raise ConfigError(f"配置键 {key!r} 必须是字符串")
        full = f"{prefix}{key}"
        if isinstance(value, Mapping):
            flat.update(_flatten(value, f"{full}."))
        else:
            flat[full] = value
    return flat


def _get_str(settings: Mapping[str, Any], key: str) -> str:
    value = settings[key]
    if not isinstance(value, str):
        raise ConfigError(f"配置项 {key} 必须是字符串，当前为 {type(value).__name__}")
    return value


def _get_int(settings: Mapping[str, Any], key: str, *, minimum: int = 1) -> int:
    value = settings[key]
    if isinstance(value, bool) or not isinstance(value, int):
        raise ConfigError(f"配置项 {key} 必须是整数，当前为 {type(value).__name__}")
    if value < minimum:
        raise ConfigError(f"配置项 {key} 不能小于 {minimum}，当前为 {value}")
    return value


def _get_float(settings: Mapping[str, Any], key: str) -> float:
    value = settings[key]
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConfigError(f"配置项 {key} 必须是数字，当前为 {type(value).__name__}")
    return float(value)


def _get_bool(settings: Mapping[str, Any], key: str) -> bool:
    value = settings[key]
    if not isinstance(value, bool):
        raise ConfigError(f"配置项 {key} 必须是布尔值，当前为 {type(value).__name__}")
    return value


def _get_str_list(settings: Mapping[str, Any], key: str) -> list[str]:
    value = settings[key]
    if not isinstance(value, list) or not value:
        raise ConfigError(f"配置项 {key} 必须是非空字符串列表")
    result: list[str] = []
    for index, item in enumerate(value):
        if not isinstance(item, str) or not item.strip():
            raise ConfigError(f"配置项 {key}[{index}] 必须是非空字符串")
        result.append(item.strip())
    if len(set(result)) != len(result):
        raise ConfigError(f"配置项 {key} 存在重复步骤")
    return result


def _resolve_path(root: Path, settings: Mapping[str, Any], key: str) -> Path:
    raw = _get_str(settings, key)
    if not raw.strip():
        raise ConfigError(f"配置项 {key} 不能为空")
    path = Path(os.path.expanduser(raw))
    if not path.is_absolute():
        path = root / path
    return path.resolve()


def _check_format(key: str, value: str) -> None:
    try:
        value.format(index=1, year=2026, month=1, date="2026-01-01", title="示例")
    except (KeyError, IndexError, ValueError) as exc:
        raise ConfigError(f"配置项 {key} 不是合法的命名模板: {value!r}") from exc


def _resolve_config_path(path: str | Path | None, env: Mapping[str, str]) -> Path | None:
    if path is not None:
        candidate = Path(os.path.expanduser(str(path)))
        return candidate.resolve()
    from_env = env.get(ENV_CONFIG_PATH)
    if from_env:
        return Path(os.path.expanduser(from_env)).resolve()
    default = Path.cwd() / CONFIG_FILENAME
    return default.resolve() if default.is_file() else None


def load_config(
    path: str | Path | None = None,
    *,
    env: Mapping[str, str] | None = None,
    overrides: Mapping[str, Any] | None = None,
) -> Config:
    """Load configuration, applying defaults, TOML, environment and CLI overrides."""

    environment = dict(os.environ if env is None else env)
    config_path = _resolve_config_path(path, environment)
    root = config_path.parent if config_path is not None else Path.cwd().resolve()

    settings = dict(DEFAULT_SETTINGS)
    if config_path is not None:
        if not config_path.is_file():
            raise ConfigError(f"配置文件不存在: {config_path}")
        try:
            with config_path.open("rb") as handle:
                raw = tomllib.load(handle)
        except tomllib.TOMLDecodeError as exc:
            raise ConfigError(f"配置文件不是合法 TOML: {config_path}: {exc}") from exc
        settings.update(_flatten(raw))

    if overrides:
        settings.update(_flatten(overrides))

    api_key = environment.get(ENV_API_KEY) or None

    naming = NamingConfig(
        dir_format=_get_str(settings, "naming.dir_format"),
        file_format=_get_str(settings, "naming.file_format"),
        max_title_chars=_get_int(settings, "naming.max_title_chars"),
    )
    _check_format("naming.dir_format", naming.dir_format)
    _check_format("naming.file_format", naming.file_format)

    publish = PublishConfig(
        enabled=_get_bool(settings, "publish.enabled"),
        provider=_get_str(settings, "publish.provider"),
        remote=_get_str(settings, "publish.remote"),
        branch=_get_str(settings, "publish.branch"),
        commit_message=_get_str(settings, "publish.commit_message"),
    )
    if publish.enabled and not publish.remote.strip():
        raise ConfigError("配置项 publish.remote 在 publish.enabled = true 时不能为空")

    return Config(
        workspace=WorkspaceConfig(
            root=root,
            work_dir=_resolve_path(root, settings, "workspace.work_dir"),
            minutes_dir=_resolve_path(root, settings, "workspace.minutes_dir"),
            state_dir=_resolve_path(root, settings, "workspace.state_dir"),
            archive_dir=_resolve_path(root, settings, "workspace.archive_dir"),
        ),
        naming=naming,
        preflight=PreflightConfig(
            silent_db=_get_float(settings, "preflight.silent_db"),
            min_words=_get_int(settings, "preflight.min_words", minimum=0),
        ),
        transcribe=TranscribeConfig(
            segment_seconds=_get_int(settings, "transcribe.segment_seconds"),
            request_seconds=_get_int(settings, "transcribe.request_seconds"),
            concurrency=_get_int(settings, "transcribe.concurrency"),
            max_retries=_get_int(settings, "transcribe.max_retries", minimum=0),
        ),
        source=SourceConfig(provider=_get_str(settings, "source.provider")),
        asr=AsrConfig(
            provider=_get_str(settings, "asr.provider"),
            model=_get_str(settings, "asr.model"),
        ),
        index=IndexConfig(enabled=_get_bool(settings, "index.enabled")),
        publish=publish,
        pipeline=PipelineConfig(steps=tuple(_get_str_list(settings, "pipeline.steps"))),
        stepfun_api_key=api_key,
        config_path=config_path,
    )
