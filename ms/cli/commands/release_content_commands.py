from __future__ import annotations

import typer

from ms.cli.commands.release_content_plan import plan_cmd
from ms.cli.commands.release_content_prepare import prepare_cmd
from ms.cli.commands.release_content_publish import publish_cmd
from ms.cli.commands.release_content_remove import remove_cmd


def register_content_commands(*, top_level: typer.Typer, namespace: typer.Typer) -> None:
    top_level.command("plan")(plan_cmd)
    top_level.command("prepare")(prepare_cmd)
    top_level.command("publish")(publish_cmd)
    top_level.command("remove")(remove_cmd)

    namespace.command("plan")(plan_cmd)
    namespace.command("prepare")(prepare_cmd)
    namespace.command("publish")(publish_cmd)
    namespace.command("remove")(remove_cmd)
