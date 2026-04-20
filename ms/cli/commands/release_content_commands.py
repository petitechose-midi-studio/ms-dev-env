from __future__ import annotations

import typer

from ms.cli.commands.release_content_plan import plan_cmd
from ms.cli.commands.release_content_prepare import prepare_cmd
from ms.cli.commands.release_content_publish import publish_cmd
from ms.cli.commands.release_content_remove import remove_cmd
from ms.cli.commands.release_content_workflow_commands import (
    fetch_content_candidate_cmd,
)


def register_content_commands(*, namespace: typer.Typer) -> None:
    namespace.command("plan")(plan_cmd)
    namespace.command("prepare")(prepare_cmd)
    namespace.command("publish")(publish_cmd)
    namespace.command("remove")(remove_cmd)
    namespace.command("fetch-candidate", hidden=True)(fetch_content_candidate_cmd)
