"""Command line entry point for feishu-minutes-kit."""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Annotated

import typer

from fmk import __version__
from fmk.config import (
    DEFAULT_CONFIG_TOML,
    ENV_EXAMPLE,
    Config,
    load_config,
)
from fmk.context import Context
from fmk.doctor import has_failures, run_checks
from fmk.errors import EXIT_CONFIG, ConfigError, FmkError, StepError
from fmk.pipeline import Pipeline
from fmk.registry import Registry
from fmk.state import STATE_FILENAME, StateStore
from fmk.steps.discover import DiscoverStep

app = typer.Typer(
    name="fmk",
    help="Turn Feishu Minutes recordings into a searchable local Markdown archive.",
    no_args_is_help=True,
    add_completion=False,
)
plugins_app = typer.Typer(help="Inspect discovered steps and providers.")
app.add_typer(plugins_app, name="plugins")


@dataclass
class AppState:
    config_path: Path | None


@app.callback()
def callback(
    ctx: typer.Context,
    config: Annotated[
        Path | None,
        typer.Option("--config", "-c", help="Path to config.toml."),
    ] = None,
) -> None:
    """Manage a local Feishu Minutes archive."""

    ctx.obj = AppState(config_path=config)


@app.command()
def version() -> None:
    """Print the installed version."""

    typer.echo(__version__)


@app.command()
def init(
    directory: Annotated[
        Path,
        typer.Option("--dir", help="Directory that receives config.toml and .env.example."),
    ] = Path(),
    force: Annotated[bool, typer.Option("--force", help="Overwrite existing files.")] = False,
) -> None:
    """Create config.toml, .env.example and the workspace directories."""

    target = directory.expanduser().resolve()
    target.mkdir(parents=True, exist_ok=True)

    config_path = target / "config.toml"
    env_path = target / ".env.example"
    if config_path.exists() and not force:
        raise ConfigError(f"{config_path} 已存在", hint="如需覆盖请加 --force")

    config_path.write_text(DEFAULT_CONFIG_TOML, encoding="utf-8")
    if force or not env_path.exists():
        env_path.write_text(ENV_EXAMPLE, encoding="utf-8")

    config = load_config(config_path, env={})
    config.ensure_directories()

    typer.echo(f"已写入 {config_path}")
    typer.echo(f"已写入 {env_path}")
    typer.echo(f"工作区 {config.workspace.root}")


@app.command()
def doctor(ctx: typer.Context) -> None:
    """Check external commands, credentials and directory permissions."""

    config = _load_config(ctx)
    checks = run_checks(config)
    for check in checks:
        typer.echo(f"[{check.status}] {check.name}: {check.detail}")
    if has_failures(checks):
        raise typer.Exit(EXIT_CONFIG)


@app.command()
def discover(
    ctx: typer.Context,
    since: Annotated[
        str | None,
        typer.Option("--since", help="Start date (YYYY-MM-DD)."),
    ] = None,
    as_json: Annotated[bool, typer.Option("--json", help="Print JSON.")] = False,
) -> None:
    """List minutes that are not archived yet."""

    config = _load_config(ctx)
    registry = Registry()
    registry.discover()
    store = StateStore(config.workspace.state_dir / STATE_FILENAME)
    store.load()
    context = Context(
        config,
        state=store,
        providers=registry.providers,
        options={"since": since},
    )
    result = DiscoverStep().run(context)
    items = context.require("minutes.list")

    if as_json:
        payload = [
            {
                "token": item.token,
                "title": item.title,
                "start": item.start.isoformat() if item.start else None,
                "duration_seconds": item.duration_seconds,
                "url": item.url,
            }
            for item in items
        ]
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    evidence = result.evidence
    typer.echo(
        f"{evidence['since']} → {evidence['until']}："
        f"获取 {evidence['fetched']} 条，已知 {evidence['known']} 条，"
        f"新增 {evidence['new']} 条"
    )
    for item in items:
        when = item.start.strftime("%Y-%m-%d %H:%M") if item.start else "-"
        typer.echo(f"  {when}  {item.token}  {item.title}")


@plugins_app.command("list")
def plugins_list() -> None:
    """List discovered steps and providers."""

    registry = Registry()
    registry.discover()

    typer.echo("步骤:")
    for step in registry.steps:
        requires = ", ".join(sorted(step.requires)) or "-"
        provides = ", ".join(sorted(step.provides)) or "-"
        typer.echo(f"  {step.name:<12} requires={requires:<16} provides={provides}")

    providers = registry.providers
    if providers:
        typer.echo("Provider:")
        for name in sorted(providers):
            typer.echo(f"  {name}")

    for warning in registry.warnings:
        typer.echo(f"警告: {warning}", err=True)


@app.command()
def run(
    ctx: typer.Context,
    only: Annotated[
        str | None,
        typer.Option("--only", help="Stop after this step (inclusive)."),
    ] = None,
    dry_run: Annotated[
        bool,
        typer.Option(
            "--dry-run",
            help="Plan without writing the archive or state and without calling ASR.",
        ),
    ] = False,
    since: Annotated[
        str | None,
        typer.Option("--since", help="Search window start (YYYY-MM-DD)."),
    ] = None,
) -> None:
    """Run the pipeline in configured order."""

    config = _load_config(ctx)
    config.ensure_directories()
    registry = Registry()
    registry.discover()
    store = StateStore(config.workspace.state_dir / STATE_FILENAME)
    store.load()

    store.state.completed_steps.clear()
    pipeline = Pipeline(registry, config.pipeline.steps)
    steps = pipeline.plan(only=only)
    if not steps:
        typer.echo("没有需要执行的步骤。")
        return

    context = Context(
        config,
        state=store,
        dry_run=dry_run,
        providers=registry.providers,
        options={"since": since},
    )
    for step in steps:
        typer.echo(f"▶ {step.name}")
        result = step.run(context)
        suffix = f"（{result.reason}）" if result.reason else ""
        typer.echo(f"  {result.status}{suffix}")
        if result.status in {"fail", "retry"}:
            raise StepError(f"步骤 {step.name} 未完成", hint=result.reason)
        if not dry_run:
            store.mark_step(step.name)

    if not dry_run and only is None:
        store.state.completed_steps.clear()
        store.state.last_search = date.today().isoformat()
        store.save()
    typer.echo("完成。" if not dry_run else "预演完成（未写入）。")


@app.command()
def status(
    ctx: typer.Context,
    as_json: Annotated[bool, typer.Option("--json", help="Print machine-readable JSON.")] = False,
) -> None:
    """Show configuration, pipeline plan and stored state."""

    config = _load_config(ctx)
    registry = Registry()
    registry.discover()
    plan = Pipeline(registry, config.pipeline.steps).plan()

    store = StateStore(config.workspace.state_dir / STATE_FILENAME)
    state = store.load()
    counts = Counter(item.status for item in state.items.values())

    if as_json:
        payload = {
            "config": str(config.config_path) if config.config_path else None,
            "workspace": str(config.workspace.root),
            "pipeline": [step.name for step in plan],
            "completed_steps": sorted(state.completed_steps),
            "last_run": state.last_run,
            "last_search": state.last_search,
            "items": {"total": len(state.items), "by_status": dict(sorted(counts.items()))},
        }
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    typer.echo(f"配置: {config.config_path or '未找到 config.toml（使用默认值）'}")
    typer.echo(f"工作区: {config.workspace.root}")
    typer.echo(f"最后运行: {state.last_run or '未运行'}")
    completed = ", ".join(sorted(state.completed_steps)) or "-"
    typer.echo(f"已完成步骤: {completed}")
    summary = ", ".join(f"{name}={count}" for name, count in sorted(counts.items())) or "-"
    typer.echo(f"条目: {len(state.items)}（{summary}）")
    typer.echo("流水线: " + " → ".join(step.name for step in plan))


def _load_config(ctx: typer.Context) -> Config:
    app_state = ctx.obj
    path = app_state.config_path if isinstance(app_state, AppState) else None
    return load_config(path)


def main() -> None:
    """Console script entry point."""

    try:
        app()
    except FmkError as exc:
        typer.secho(f"错误: {exc.render()}", err=True, fg=typer.colors.RED)
        raise SystemExit(exc.exit_code) from exc
