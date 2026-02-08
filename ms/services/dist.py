"""Distribution packaging + manifest generation.

This service is primarily used by CI workflows to package the final binaries
that the end-user installer will manage.

Design goals:

- Deterministic output file names (stable asset IDs)
- Cross-platform (Windows/macOS/Linux)
- Avoid shipping developer/local state (e.g. macros.bin, .pdb)
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from ms.core.result import Err
from ms.platform.detection import Arch, Platform, detect
from ms.platform.process import run as run_process


@dataclass(frozen=True, slots=True)
class DistAsset:
    asset_id: str
    filename: str
    kind: str
    os: str | None
    arch: str | None
    size: int
    sha256: str


def _arch_str(arch: Arch) -> str:
    return {Arch.X64: "x86_64", Arch.ARM64: "arm64"}.get(arch, "unknown")


def _platform_str(platform: Platform) -> str:
    return {Platform.WINDOWS: "windows", Platform.MACOS: "macos", Platform.LINUX: "linux"}.get(
        platform, "unknown"
    )


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _zip_files(zip_path: Path, *, files: list[tuple[Path, str]]) -> None:
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    # Some CI environments ship tool files with mtime=0 (Unix epoch). The ZIP
    # format cannot represent timestamps before 1980, and Python defaults to
    # strict timestamp validation.
    with ZipFile(zip_path, "w", compression=ZIP_DEFLATED, strict_timestamps=False) as zf:
        for src, arc in files:
            zf.write(src, arcname=arc)


def _collect_dir(
    base_dir: Path,
    *,
    arc_prefix: str,
    exclude_names: set[str] | None = None,
    exclude_suffixes: tuple[str, ...] = (),
) -> list[tuple[Path, str]]:
    if not base_dir.exists():
        return []

    exclude_names = exclude_names or set()
    out: list[tuple[Path, str]] = []
    for p in sorted(base_dir.rglob("*")):
        if p.is_dir():
            continue
        if p.name in exclude_names:
            continue
        if exclude_suffixes and any(p.name.endswith(s) for s in exclude_suffixes):
            continue
        rel = p.relative_to(base_dir).as_posix()
        out.append((p, f"{arc_prefix}/{rel}"))
    return out


def package_platform(
    *,
    workspace_root: Path,
    out_dir: Path,
    include_wasm: bool = False,
    include_extension: bool = False,
    include_firmware: bool = False,
    require_uploader: bool = False,
) -> list[Path]:
    """Package current platform outputs into zip assets.

    Returns a list of created zip file paths.
    """
    info = detect()
    os_str = _platform_str(info.platform)
    arch_str = _arch_str(info.arch)

    bin_dir = workspace_root / "bin"

    created: list[Path] = []

    # Native bundle (bridge + native simulators)
    native_zip = out_dir / f"midi-studio-{os_str}-{arch_str}-native.zip"
    native_files: list[tuple[Path, str]] = []

    # Bridge
    native_files += _collect_dir(
        bin_dir / "bridge",
        arc_prefix="bridge",
        exclude_suffixes=(".pdb",),
    )

    # Core native (exclude local state + debug)
    native_files += _collect_dir(
        bin_dir / "core" / "native",
        arc_prefix="core/native",
        exclude_names={"macros.bin"},
        exclude_suffixes=(".pdb",),
    )

    # Bitwig native
    native_files += _collect_dir(
        bin_dir / "bitwig" / "native",
        arc_prefix="bitwig/native",
        exclude_suffixes=(".pdb",),
    )

    if native_files:
        _zip_files(native_zip, files=native_files)
        created.append(native_zip)

    # Teensy uploader CLI bundle (per-platform)
    #
    # We ship our own MIT/Apache uploader (midi-studio-loader) rather than PJRC's
    # teensy_loader_cli.
    uploader_zip = out_dir / f"midi-studio-{os_str}-{arch_str}-teensy-uploader.zip"
    uploader_files: list[tuple[Path, str]] = []
    loader_dir = workspace_root / "midi-studio" / "loader" / "target" / "release"
    loader_name = (
        "midi-studio-loader.exe" if info.platform == Platform.WINDOWS else "midi-studio-loader"
    )
    loader_bin = loader_dir / loader_name

    if loader_bin.exists() and loader_bin.is_file():
        uploader_files.append((loader_bin, f"teensy/{loader_name}"))

    if uploader_files:
        _zip_files(uploader_zip, files=uploader_files)
        created.append(uploader_zip)
    elif require_uploader:
        raise FileNotFoundError(
            "midi-studio-loader not found (expected built Rust uploader). "
            "Build it with: (cd midi-studio/loader) cargo build --release"
        )

    # WASM bundles (Ubuntu-only in CI, but works everywhere if outputs exist)
    if include_wasm:
        core_wasm = bin_dir / "core" / "wasm"
        bitwig_wasm = bin_dir / "bitwig" / "wasm"

        core_zip = out_dir / "midi-studio-wasm-core.zip"
        core_files = _collect_dir(core_wasm, arc_prefix="core/wasm")
        if core_files:
            _zip_files(core_zip, files=core_files)
            created.append(core_zip)
        else:
            raise FileNotFoundError(f"WASM output missing: {core_wasm}")

        bitwig_zip = out_dir / "midi-studio-wasm-bitwig.zip"
        bitwig_files = _collect_dir(bitwig_wasm, arc_prefix="bitwig/wasm")
        if bitwig_files:
            _zip_files(bitwig_zip, files=bitwig_files)
            created.append(bitwig_zip)
        else:
            raise FileNotFoundError(f"WASM output missing: {bitwig_wasm}")

    # Bitwig extension bundle (OS-independent, but build runs on the current host)
    if include_extension:
        ext_path = bin_dir / "bitwig" / "midi_studio.bwextension"
        if not ext_path.exists():
            raise FileNotFoundError(f"Bitwig extension missing: {ext_path}")
        ext_zip = out_dir / "midi-studio-bitwig-extension.zip"
        _zip_files(ext_zip, files=[(ext_path, "bitwig/midi_studio.bwextension")])
        created.append(ext_zip)

    # Firmware bundle (we build on one platform in CI; package if present)
    if include_firmware:
        fw_files: list[tuple[Path, str]] = []
        fw_core = bin_dir / "core" / "teensy" / "dev" / "firmware.hex"
        fw_bitwig = bin_dir / "bitwig" / "teensy" / "dev" / "firmware.hex"
        if fw_core.exists():
            fw_files.append((fw_core, "firmware/core/dev/firmware.hex"))
        if fw_bitwig.exists():
            fw_files.append((fw_bitwig, "firmware/bitwig/dev/firmware.hex"))

        if fw_files:
            fw_zip = out_dir / "midi-studio-firmware-teensy.zip"
            _zip_files(fw_zip, files=fw_files)
            created.append(fw_zip)
        else:
            raise FileNotFoundError("Firmware outputs missing in bin/*/teensy/dev/firmware.hex")

    return created


def generate_manifest(
    *,
    workspace_root: Path,
    dist_dir: Path,
    channel: str,
    tag: str,
    out_path: Path,
    source_hash: str | None = None,
) -> Path:
    """Generate a manifest.json from dist assets and repo lock."""
    dist_dir = dist_dir.resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    ms_dev_env_sha = _git_rev_parse(workspace_root)
    repos = _load_repos_lock(workspace_root)

    # Default source_hash is stable across platforms (ms sha + repo head shas)
    if source_hash is None:
        h = hashlib.sha256()
        h.update(ms_dev_env_sha.encode("ascii"))
        for r in repos:
            org = str(r.get("org", ""))
            name = str(r.get("name", ""))
            head = str(r.get("head_sha", ""))
            h.update(b"\n")
            h.update((org + "/" + name).encode("ascii", "ignore"))
            h.update(b"@")
            h.update(head.encode("ascii", "ignore"))
        source_hash = h.hexdigest()

    assets: list[DistAsset] = []
    for p in sorted(dist_dir.glob("*.zip")):
        size = p.stat().st_size
        sha256 = _sha256_file(p)
        asset_id, kind, os_name, arch = _infer_asset_metadata(p.name)
        assets.append(
            DistAsset(
                asset_id=asset_id,
                filename=p.name,
                kind=kind,
                os=os_name,
                arch=arch,
                size=size,
                sha256=sha256,
            )
        )

    manifest = {
        "schema": 1,
        "channel": channel,
        "tag": tag,
        "source_hash": source_hash,
        "ms_dev_env_sha": ms_dev_env_sha,
        "repos": repos,
        "assets": [
            {
                "id": a.asset_id,
                "filename": a.filename,
                "kind": a.kind,
                "os": a.os,
                "arch": a.arch,
                "size": a.size,
                "sha256": a.sha256,
            }
            for a in assets
        ],
    }

    out_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return out_path


def _infer_asset_metadata(filename: str) -> tuple[str, str, str | None, str | None]:
    """Infer (asset_id, kind, os, arch) from our deterministic filenames."""
    if filename.startswith("midi-studio-wasm-core"):
        return "simulator_wasm_core", "simulator_wasm", None, None
    if filename.startswith("midi-studio-wasm-bitwig"):
        return "simulator_wasm_bitwig", "simulator_wasm", None, None
    if filename == "midi-studio-bitwig-extension.zip":
        return "bitwig_extension", "extension", None, None
    if filename == "midi-studio-firmware-teensy.zip":
        return "firmware_teensy", "firmware", None, None

    # Platform-scoped bundles
    if filename.startswith("midi-studio-"):
        parts = filename.removesuffix(".zip").split("-")
        # midi-studio-<os>-<arch>-<kind>
        if len(parts) >= 4:
            os_name = parts[2]
            arch = parts[3]
            suffix = "-".join(parts[4:])
            if suffix == "native":
                return f"bundle_native_{os_name}_{arch}", "bundle_native", os_name, arch
            if suffix == "teensy-uploader":
                return f"teensy_uploader_{os_name}_{arch}", "uploader", os_name, arch

    return f"asset_{filename}", "unknown", None, None


def _git_rev_parse(workspace_root: Path) -> str:
    out = run_process(["git", "rev-parse", "HEAD"], cwd=workspace_root, timeout=30.0)
    if isinstance(out, Err):
        return "unknown"
    return out.value.strip()


def _load_repos_lock(workspace_root: Path) -> list[dict[str, object]]:
    lock_path = workspace_root / ".ms" / "repos.lock.json"
    if lock_path.exists():
        try:
            return json.loads(lock_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            pass

    # Fallback: best-effort, scan known clone roots.
    repos: list[dict[str, object]] = []
    for base in (workspace_root / "open-control", workspace_root / "midi-studio"):
        if not base.exists():
            continue
        for child in sorted(base.iterdir()):
            if not child.is_dir() or not (child / ".git").exists():
                continue
            sha = _git_rev_parse(child)
            repos.append(
                {"org": base.name, "name": child.name, "path": str(child), "head_sha": sha}
            )
    return repos


def read_manifest(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_text_atomic(path: Path, content: str) -> None:
    tmp = Path(f"{path}.tmp")
    tmp.write_text(content, encoding="utf-8")
    os.replace(tmp, path)
