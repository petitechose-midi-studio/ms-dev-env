from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from ms.core.result import Result
from ms.output.console import ConsoleProtocol
from ms.release.domain.models import ReleasePlan
from ms.release.errors import ReleaseError


def publish_content_release(
    *,
    publish_distribution_release_fn: Callable[..., Result[str, ReleaseError]],
    workspace_root: Path,
    console: ConsoleProtocol,
    plan: ReleasePlan,
    watch: bool,
    dry_run: bool,
) -> Result[str, ReleaseError]:
    return publish_distribution_release_fn(
        workspace_root=workspace_root,
        console=console,
        plan=plan,
        watch=watch,
        dry_run=dry_run,
    )
