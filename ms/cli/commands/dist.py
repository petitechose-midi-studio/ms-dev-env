from __future__ import annotations

from pathlib import Path

import typer

from ms.cli.context import build_context
from ms.services.dist import generate_manifest, package_platform

dist_app = typer.Typer(add_completion=False, no_args_is_help=True)


@dist_app.command("package")
def package_cmd(
    out: Path = typer.Option(Path("dist"), "--out", help="Output directory"),
    wasm: bool = typer.Option(False, "--wasm", help="Include WASM bundles if present"),
    extension: bool = typer.Option(
        False, "--extension", help="Include Bitwig extension bundle if present"
    ),
    firmware: bool = typer.Option(False, "--firmware", help="Include firmware bundle if present"),
    require_uploader: bool = typer.Option(
        False,
        "--require-uploader",
        help="Fail if Teensy uploader CLI is missing (CI mode)",
    ),
) -> None:
    """Package final binaries for distribution (CI helper)."""
    ctx = build_context()
    created = package_platform(
        workspace_root=ctx.workspace.root,
        out_dir=(ctx.workspace.root / out),
        include_wasm=wasm,
        include_extension=extension,
        include_firmware=firmware,
        require_uploader=require_uploader,
    )

    for p in created:
        ctx.console.success(str(p))


@dist_app.command("manifest")
def manifest_cmd(
    channel: str = typer.Option(..., "--channel", help="Channel: nightly|release"),
    tag: str = typer.Option(..., "--tag", help="Release tag (e.g. nightly-2026-01-29, v0.1.0)"),
    dist_dir: Path = typer.Option(Path("dist"), "--dist-dir", help="Directory of dist zips"),
    out: Path = typer.Option(Path("dist/manifest.json"), "--out", help="Output manifest path"),
    source_hash: str | None = typer.Option(
        None, "--source-hash", help="Optional precomputed source hash"
    ),
) -> None:
    """Generate a manifest.json for a dist directory."""
    ctx = build_context()
    out_path = generate_manifest(
        workspace_root=ctx.workspace.root,
        dist_dir=(ctx.workspace.root / dist_dir),
        channel=channel,
        tag=tag,
        out_path=(ctx.workspace.root / out),
        source_hash=source_hash,
    )
    ctx.console.success(str(out_path))
