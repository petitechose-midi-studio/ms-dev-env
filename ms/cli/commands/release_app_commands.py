from __future__ import annotations

import typer

from ms.cli.commands.release_app_plan import app_plan_cmd
from ms.cli.commands.release_app_prepare import app_prepare_cmd
from ms.cli.commands.release_app_publish import app_publish_cmd


def register_app_commands(*, namespace: typer.Typer) -> None:
    namespace.command("plan")(app_plan_cmd)
    namespace.command("prepare")(app_prepare_cmd)
    namespace.command("publish")(app_publish_cmd)
