"""Publish the archive when enabled in configuration."""

from __future__ import annotations

from dataclasses import asdict

from fmk.context import Context
from fmk.core.naming import scan_archive
from fmk.errors import ConfigError
from fmk.providers.base import API_VERSION, Publisher
from fmk.providers.git_publisher import GitPublisher
from fmk.state import ItemState
from fmk.steps.base import StepResult


class PublishStep:
    """Commit and push the archive, or skip cleanly when disabled."""

    api_version = API_VERSION
    name = "publish"
    requires: frozenset[str] = frozenset({"archive.path"})
    provides: frozenset[str] = frozenset({"publish.result"})

    def run(self, ctx: Context) -> StepResult:
        ctx.require("archive.path")
        config = ctx.config
        if not config.publish.enabled:
            payload = {"skipped": True, "reason": "publish.enabled=false"}
            ctx.set("publish.result", payload, step=self.name, provides=self.provides)
            ctx.logger.info("publish: 已在配置中关闭，跳过")
            return StepResult(
                status="skip", outputs={"publish.result": payload}, reason="publish.enabled=false"
            )

        provider = ctx.provider(config.publish.provider)
        if not isinstance(provider, Publisher):
            if config.publish.provider == "git":
                provider = GitPublisher()
            else:
                raise ConfigError(f"provider {config.publish.provider} 未实现 Publisher 协议")

        result = provider.publish(
            config.workspace.archive_dir,
            remote=config.publish.remote,
            branch=config.publish.branch,
            message=config.publish.commit_message,
            dry_run=ctx.dry_run,
        )
        payload = asdict(result)
        ctx.set("publish.result", payload, step=self.name, provides=self.provides)

        if not ctx.dry_run:
            items = scan_archive(config.workspace.archive_dir)
            updates = {
                item.token: ItemState(
                    status="published",
                    words=item.words,
                    files=[item.path.relative_to(config.workspace.archive_dir).as_posix()],
                )
                for item in items
            }
            if ctx.state is not None and updates:
                ctx.state.update_items(updates)

        label = f"提交 {result.commit[:8]}" if result.committed and result.commit else "无变更"
        ctx.logger.info("publish: %s，文件 %d 个", label, result.changed_files)
        return StepResult(
            status="ok",
            outputs={"publish.result": payload},
            evidence={**payload, "dry_run": ctx.dry_run},
        )
