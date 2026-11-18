"""Built-in pipeline steps."""

from __future__ import annotations

from fmk.steps.base import Step, StepResult
from fmk.steps.compose import ComposeStep
from fmk.steps.discover import DiscoverStep
from fmk.steps.download import DownloadStep
from fmk.steps.index import IndexStep
from fmk.steps.organize import OrganizeStep
from fmk.steps.preflight import PreflightStep
from fmk.steps.publish import PublishStep
from fmk.steps.reconcile import ReconcileStep
from fmk.steps.transcribe import TranscribeStep

__all__ = ["Step", "StepResult", "builtin_steps"]


def builtin_steps() -> list[Step]:
    """Return the nine built-in steps in their default order."""

    return [
        DiscoverStep(),
        DownloadStep(),
        PreflightStep(),
        TranscribeStep(),
        ComposeStep(),
        OrganizeStep(),
        ReconcileStep(),
        IndexStep(),
        PublishStep(),
    ]
