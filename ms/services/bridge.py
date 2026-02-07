from __future__ import annotations

import hashlib
import shutil
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from ms.core.config import Config
from ms.core.errors import ErrorCode
from ms.core.result import Err, Ok, Result
from ms.core.structured import as_str_dict, get_str
from ms.core.versions import RUST_MIN_VERSION, RUST_MIN_VERSION_TEXT
from ms.core.workspace import Workspace
from ms.output.console import ConsoleProtocol, Style
from ms.platform.detection import PlatformInfo
from ms.platform.process import run, run_silent
from ms.services.checkers.common import format_version_triplet, parse_version_triplet
from ms.tools.download import Downloader
from ms.tools.http import HttpClient, RealHttpClient

if TYPE_CHECKING:
    from ms.platform.detection import Arch, Platform


_CARGO_BUILD_TIMEOUT_SECONDS = 30 * 60.0

# -----------------------------------------------------------------------------
# Error Types
# -----------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class BridgeError:
    """Error from bridge operations."""

    kind: Literal[
        "dir_missing",
        "cargo_missing",
        "rustc_missing",
        "rust_too_old",
        "linker_missing",
        "build_failed",
        "binary_missing",
        "download_failed",
        "release_metadata_failed",
        "checksum_manifest_invalid",
        "checksum_missing",
        "checksum_mismatch",
        "unsupported_platform",
    ]
    message: str
    hint: str | None = None


def _get_linker_hint(platform: PlatformInfo) -> str:
    """Get platform-specific hint for installing C linker."""
    from ms.platform.detection import LinuxDistro, Platform

    if platform.platform == Platform.WINDOWS:
        return "Install Build Tools: https://visualstudio.microsoft.com/visual-cpp-build-tools/"
    if platform.platform == Platform.MACOS:
        return "Run: xcode-select --install"
    # Linux - check distro
    if platform.distro == LinuxDistro.FEDORA:
        return "Run: sudo dnf install gcc"
    if platform.distro == LinuxDistro.ARCH:
        return "Run: sudo pacman -S base-devel"
    # Default to Debian/Ubuntu
    return "Run: sudo apt install build-essential"


def _has_c_linker() -> bool:
    """Check if a C compiler/linker is available."""
    return shutil.which("cc") is not None or shutil.which("gcc") is not None


class BridgeService:
    def __init__(
        self,
        *,
        workspace: Workspace,
        platform: PlatformInfo,
        config: Config | None,
        console: ConsoleProtocol,
    ) -> None:
        self._workspace = workspace
        self._platform = platform
        self._config = config
        self._console = console

    def build(self, *, release: bool = True, dry_run: bool = False) -> Result[Path, BridgeError]:
        bridge_dir = self._bridge_dir()
        if not bridge_dir.is_dir():
            return Err(
                BridgeError(
                    kind="dir_missing",
                    message=f"bridge dir missing: {bridge_dir}",
                    hint="Run: uv run ms sync --repos",
                )
            )

        if shutil.which("cargo") is None:
            return Err(
                BridgeError(
                    kind="cargo_missing",
                    message="cargo: missing",
                    hint="Install rustup: https://rustup.rs",
                )
            )

        if shutil.which("rustc") is None:
            return Err(
                BridgeError(
                    kind="rustc_missing",
                    message=f"rustc: missing (>= {RUST_MIN_VERSION_TEXT} required)",
                    hint="Install rustup: https://rustup.rs",
                )
            )

        rustc_version = run(["rustc", "--version"], cwd=bridge_dir)
        match rustc_version:
            case Ok(stdout):
                parsed = parse_version_triplet(stdout)
                if parsed is not None and parsed < RUST_MIN_VERSION:
                    found = format_version_triplet(parsed)
                    return Err(
                        BridgeError(
                            kind="rust_too_old",
                            message=(
                                f"rustc too old (found {found}, need >= {RUST_MIN_VERSION_TEXT})"
                            ),
                            hint="Install rustup: https://rustup.rs",
                        )
                    )
            case Err(_):
                # If we can't read the version, proceed and let cargo report errors.
                pass

        # Rust needs a C linker (cc/gcc) to link binaries
        if not _has_c_linker():
            return Err(
                BridgeError(
                    kind="linker_missing",
                    message="C linker (cc/gcc): missing",
                    hint=_get_linker_hint(self._platform),
                )
            )

        cmd = ["cargo", "build", "--locked"]
        if release:
            cmd.append("--release")

        self._console.print(" ".join(cmd), Style.DIM)
        dst = self._installed_bridge_bin()
        if dry_run:
            self._console.print(f"would install bridge -> {dst}", Style.DIM)
            return Ok(dst)

        result = run_silent(cmd, cwd=bridge_dir, timeout=_CARGO_BUILD_TIMEOUT_SECONDS)
        if isinstance(result, Err):
            return Err(BridgeError(kind="build_failed", message="bridge build failed"))

        built = self._built_bridge_bin(bridge_dir, release=release)
        if not built.exists():
            return Err(
                BridgeError(
                    kind="binary_missing",
                    message=f"bridge binary missing: {built}",
                )
            )

        self._console.print(f"install bridge -> {dst}", Style.DIM)

        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(built, dst)
        if self._platform.platform.is_unix:
            dst.chmod(0o755)

        src_config = bridge_dir / "config"
        if src_config.is_dir():
            shutil.copytree(src_config, dst.parent / "config", dirs_exist_ok=True)

        self._console.success(str(dst))
        return Ok(dst)

    def install_prebuilt(
        self,
        *,
        version: str | None = None,
        force: bool = False,
        strict: bool = True,
        dry_run: bool = False,
    ) -> Result[Path, BridgeError]:
        """Install oc-bridge from GitHub releases.

        This is the default installation path for end-users (no Rust required).
        """
        platform = self._platform.platform
        arch = self._platform.arch

        asset = _asset_name_for_platform(platform=platform, arch=arch)
        if asset is None:
            return Err(
                BridgeError(
                    kind="unsupported_platform",
                    message=f"no prebuilt oc-bridge for {self._platform}",
                    hint="Try: uv run ms bridge build (requires Rust)",
                )
            )

        dst = self._installed_bridge_bin()

        if dst.exists() and not force:
            self._console.success(str(dst))
            return Ok(dst)

        requested_tag = _normalize_release_tag(version)
        url = _release_asset_url(asset, version=requested_tag)
        self._console.print(f"download {url}", Style.DIM)
        if dry_run:
            self._console.print(f"would install bridge -> {dst}", Style.DIM)
            return Ok(dst)

        http = RealHttpClient()
        release_tag_result = _resolve_release_tag(version=version, http=http)
        if isinstance(release_tag_result, Err):
            return release_tag_result
        release_tag = release_tag_result.value
        url = _release_asset_url(asset, version=release_tag)

        downloader = Downloader(http, self._workspace.download_cache_dir)
        downloaded = downloader.download(url, force=force)
        if isinstance(downloaded, Err):
            e = downloaded.error
            return Err(
                BridgeError(
                    kind="download_failed",
                    message=f"download failed for {asset}@{release_tag}: {e}",
                    hint=f"asset={asset} version={release_tag}",
                )
            )

        checksums = _load_bridge_checksums(path=_bridge_checksums_path())
        if isinstance(checksums, Err):
            return checksums

        verified = _verify_prebuilt_checksum(
            checksums=checksums.value,
            release_tag=release_tag,
            asset=asset,
            downloaded_path=downloaded.value.path,
            strict=strict,
        )
        if isinstance(verified, Err):
            return verified
        if strict:
            self._console.print(f"checksum ok {asset}@{release_tag}", Style.DIM)

        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(downloaded.value.path, dst)
        if self._platform.platform.is_unix:
            dst.chmod(0o755)

        # Best-effort: copy config presets next to the binary.
        bridge_dir = self._bridge_dir()
        src_config = bridge_dir / "config"
        if src_config.is_dir():
            shutil.copytree(src_config, dst.parent / "config", dirs_exist_ok=True)

        self._console.success(str(dst))
        return Ok(dst)

    def run(self, *, args: list[str]) -> int:
        exe = self._installed_bridge_bin()
        if not exe.exists():
            # Fall back to build output.
            bridge_dir = self._bridge_dir()
            exe = self._built_bridge_bin(bridge_dir, release=True)

        if not exe.exists():
            self._console.error(f"oc-bridge not found: {exe}")
            self._console.print("hint: Run: uv run ms bridge install", Style.DIM)
            return int(ErrorCode.ENV_ERROR)

        cmd = [str(exe), *args]
        self._console.print(" ".join(cmd), Style.DIM)
        result = run_silent(cmd, cwd=self._workspace.root, timeout=None)
        match result:
            case Ok(_):
                return 0
            case Err(e):
                return e.returncode
            case _:
                return int(ErrorCode.ENV_ERROR)

    def _bridge_dir(self) -> Path:
        rel = self._config.paths.bridge if self._config is not None else "open-control/bridge"
        return self._workspace.root / rel

    def _built_bridge_bin(self, bridge_dir: Path, *, release: bool) -> Path:
        profile = "release" if release else "debug"
        exe_name = self._platform.platform.exe_name("oc-bridge")
        return bridge_dir / "target" / profile / exe_name

    def _installed_bridge_bin(self) -> Path:
        exe_name = self._platform.platform.exe_name("oc-bridge")
        return self._workspace.bin_dir / "bridge" / exe_name

    def is_installed(self) -> bool:
        """Check if bridge binary is installed."""
        return self._installed_bridge_bin().exists()


def _asset_name_for_platform(*, platform: Platform, arch: Arch) -> str | None:
    from ms.platform.detection import Arch, Platform

    match platform:
        case Platform.WINDOWS:
            return "oc-bridge-windows.exe" if arch == Arch.X64 else None
        case Platform.LINUX:
            return "oc-bridge-linux" if arch == Arch.X64 else None
        case Platform.MACOS:
            if arch == Arch.X64:
                return "oc-bridge-macos-x64"
            if arch == Arch.ARM64:
                return "oc-bridge-macos-arm64"
            return None
        case _:
            return None


_BRIDGE_RELEASES_LATEST_URL = "https://api.github.com/repos/open-control/bridge/releases/latest"


def _bridge_checksums_path() -> Path:
    return Path(__file__).parent.parent / "data" / "bridge_checksums.toml"


def _normalize_release_tag(version: str | None) -> str | None:
    if version is None:
        return None
    v = version.strip()
    if not v:
        return None
    return v if v.startswith("v") else f"v{v}"


def _resolve_release_tag(*, version: str | None, http: HttpClient) -> Result[str, BridgeError]:
    explicit = _normalize_release_tag(version)
    if explicit is not None:
        return Ok(explicit)

    latest = http.get_json(_BRIDGE_RELEASES_LATEST_URL)
    if isinstance(latest, Err):
        e = latest.error
        return Err(
            BridgeError(
                kind="release_metadata_failed",
                message=f"failed to resolve latest bridge release: {e}",
                hint=_BRIDGE_RELEASES_LATEST_URL,
            )
        )

    tag = get_str(latest.value, "tag_name")
    if tag is None:
        return Err(
            BridgeError(
                kind="release_metadata_failed",
                message="missing tag_name in bridge release metadata",
                hint=_BRIDGE_RELEASES_LATEST_URL,
            )
        )

    normalized = _normalize_release_tag(tag)
    if normalized is None:
        return Err(
            BridgeError(
                kind="release_metadata_failed",
                message=f"invalid release tag from metadata: {tag!r}",
                hint=_BRIDGE_RELEASES_LATEST_URL,
            )
        )
    return Ok(normalized)


def _load_bridge_checksums(*, path: Path) -> Result[dict[str, str], BridgeError]:
    try:
        with path.open("rb") as f:
            data_obj: object = tomllib.load(f)
    except (OSError, tomllib.TOMLDecodeError) as e:
        return Err(
            BridgeError(
                kind="checksum_manifest_invalid",
                message=f"failed to load bridge checksum manifest: {e}",
                hint=str(path),
            )
        )

    data = as_str_dict(data_obj)
    if data is None:
        return Err(
            BridgeError(
                kind="checksum_manifest_invalid",
                message="invalid bridge checksum manifest root",
                hint=str(path),
            )
        )

    schema = data.get("schema")
    if schema != 1:
        return Err(
            BridgeError(
                kind="checksum_manifest_invalid",
                message=f"unsupported bridge checksum schema: {schema}",
                hint=str(path),
            )
        )

    raw_checksums = as_str_dict(data.get("checksums"))
    if raw_checksums is None:
        return Err(
            BridgeError(
                kind="checksum_manifest_invalid",
                message="missing [checksums] table in bridge checksum manifest",
                hint=str(path),
            )
        )

    checksums: dict[str, str] = {}
    for key, value in raw_checksums.items():
        if not isinstance(value, str):
            return Err(
                BridgeError(
                    kind="checksum_manifest_invalid",
                    message=f"invalid checksum value for key: {key}",
                    hint=str(path),
                )
            )
        digest = value.strip().lower()
        if not _is_sha256(digest):
            return Err(
                BridgeError(
                    kind="checksum_manifest_invalid",
                    message=f"invalid sha256 digest for key: {key}",
                    hint=digest,
                )
            )
        checksums[key.strip()] = digest

    return Ok(checksums)


def _verify_prebuilt_checksum(
    *,
    checksums: dict[str, str],
    release_tag: str,
    asset: str,
    downloaded_path: Path,
    strict: bool,
) -> Result[None, BridgeError]:
    key = f"{release_tag}:{asset}"
    expected = checksums.get(key)
    if expected is None:
        if not strict:
            return Ok(None)
        return Err(
            BridgeError(
                kind="checksum_missing",
                message=f"missing checksum for bridge asset {asset}@{release_tag}",
                hint=f"add key '{key}' to {_bridge_checksums_path()}",
            )
        )

    actual = _sha256_file(downloaded_path)
    if actual != expected:
        return Err(
            BridgeError(
                kind="checksum_mismatch",
                message=f"checksum mismatch for bridge asset {asset}@{release_tag}",
                hint=f"expected {expected}, got {actual}",
            )
        )
    return Ok(None)


def _is_sha256(value: str) -> bool:
    if len(value) != 64:
        return False
    return all(ch in "0123456789abcdef" for ch in value)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            chunk = f.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _release_asset_url(asset: str, *, version: str | None) -> str:
    tag = _normalize_release_tag(version)
    if tag is None:
        return f"https://github.com/open-control/bridge/releases/latest/download/{asset}"
    return f"https://github.com/open-control/bridge/releases/download/{tag}/{asset}"
