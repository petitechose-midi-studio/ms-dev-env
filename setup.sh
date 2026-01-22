#!/usr/bin/env bash
# =============================================================================
# MIDI Studio / Open Control - Development Environment Bootstrap
# =============================================================================
# Clone repos + install workspace-managed tools (safe, idempotent)
#
# Usage: ./setup.sh [--skip-tools] [--skip-repos] [--skip-shell]
#
# Prerequisites:
#   All OS:   git, gh (GitHub CLI authenticated), curl, tar, unzip
#   Linux:    SDL2 + ALSA dev packages (see check_system_deps for commands)
#   macOS:    Homebrew + SDL2 (brew install sdl2)
#   Windows:  Git for Windows (provides Git Bash to run this script)
#
# Notes:
# - This script installs missing tools only (no upgrades).
# - Repo updates and tool upgrades are handled by `ms update`.
# =============================================================================

set -euo pipefail

WORKSPACE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TOOLS_DIR="$WORKSPACE/tools"

# =============================================================================
# Colors & Logging
# =============================================================================
if [[ -t 1 ]]; then
    RED='\033[0;31m'
    GREEN='\033[0;32m'
    YELLOW='\033[0;33m'
    BLUE='\033[0;34m'
    NC='\033[0m'
else
    RED='' GREEN='' YELLOW='' BLUE='' NC=''
fi

log_info()  { echo -e "${BLUE}[INFO]${NC} $*"; }
log_ok()    { echo -e "${GREEN}[OK]${NC} $*"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }
log_error() { echo -e "${RED}[ERROR]${NC} $*"; }

# Detect CI/non-interactive mode
INTERACTIVE=1
if [[ -n "${CI:-}" ]] || [[ ! -t 0 ]]; then
    INTERACTIVE=0
fi

# =============================================================================
# OS / Architecture Detection
# =============================================================================
detect_platform() {
    case "$(uname -s)" in
        Linux*)  OS="linux" ;;
        Darwin*) OS="macos" ;;
        MINGW*|MSYS*|CYGWIN*) OS="windows" ;;
        *) log_error "Unsupported OS: $(uname -s)"; exit 1 ;;
    esac

    case "$(uname -m)" in
        x86_64|amd64) ARCH="x64" ;;
        aarch64|arm64) ARCH="arm64" ;;
        *) log_error "Unsupported architecture: $(uname -m)"; exit 1 ;;
    esac

    log_info "Platform: $OS-$ARCH"
}

# =============================================================================
# Prerequisites Check (minimal)
# =============================================================================
check_prerequisites() {
    log_info "Checking prerequisites..."
    local failed=0

    # Windows note: this script requires Git Bash (comes with Git for Windows)
    if [[ "$OS" == "windows" ]]; then
        log_info "Windows: running in Git Bash (from Git for Windows)"
    fi

    # Git
    if ! command -v git &>/dev/null; then
        log_error "git not found"
        echo "  Linux:   sudo apt install git"
        echo "  macOS:   xcode-select --install"
        echo "  Windows: winget install Git.Git"
        failed=1
    fi

    # GitHub CLI
    if ! command -v gh &>/dev/null; then
        log_error "gh (GitHub CLI) not found"
        echo "  Linux:   sudo apt install gh  OR  https://cli.github.com/"
        echo "  macOS:   brew install gh"
        echo "  Windows: winget install GitHub.cli"
        failed=1
    elif ! gh auth status &>/dev/null 2>&1; then
        log_error "GitHub CLI not authenticated"
        echo "  Run: gh auth login"
        failed=1
    fi

    # curl
    if ! command -v curl &>/dev/null; then
        log_error "curl not found"
        echo "  Linux:   sudo apt install curl"
        echo "  macOS:   brew install curl"
        echo "  Windows: bundled with Git for Windows (Git Bash)"
        failed=1
    fi

    # tar
    if ! command -v tar &>/dev/null; then
        log_error "tar not found"
        echo "  Linux:   sudo apt install tar"
        echo "  macOS:   built-in"
        echo "  Windows: bundled with Git for Windows (Git Bash)"
        failed=1
    fi

    # unzip
    if ! command -v unzip &>/dev/null; then
        log_error "unzip not found"
        echo "  Linux:   sudo apt install unzip"
        echo "  macOS:   brew install unzip"
        echo "  Windows: bundled with Git for Windows (Git Bash)"
        failed=1
    fi

    if [[ $failed -eq 1 ]]; then
        exit 1
    fi

    log_ok "Prerequisites OK"
}

# =============================================================================
# System Dependencies Check (SDL2, ALSA - no sudo, just verify)
# =============================================================================
check_system_deps() {
    log_info "Checking system dependencies..."
    local missing=()

    case "$OS" in
        linux)
            # Check pkg-config exists
            if ! command -v pkg-config &>/dev/null; then
                log_error "pkg-config not found (needed to check dependencies)"
                echo "  Install: sudo apt install pkg-config  OR  sudo dnf install pkgconf-pkg-config"
                exit 1
            fi

            # SDL2
            if ! pkg-config --exists sdl2 2>/dev/null; then
                missing+=("SDL2")
            fi

            # ALSA (needed for libremidi MIDI support)
            if ! pkg-config --exists alsa 2>/dev/null; then
                missing+=("ALSA")
            fi

            if [[ ${#missing[@]} -gt 0 ]]; then
                log_error "Missing system dependencies: ${missing[*]}"
                echo ""
                echo "Install with your package manager:"
                echo "  Fedora/RHEL:   sudo dnf install SDL2-devel alsa-lib-devel"
                echo "  Ubuntu/Debian: sudo apt install libsdl2-dev libasound2-dev"
                echo "  Arch:          sudo pacman -S sdl2 alsa-lib"
                echo "  openSUSE:      sudo zypper install SDL2-devel alsa-devel"
                echo ""
                echo "Then re-run: ./setup.sh"
                exit 1
            fi
            ;;
        macos)
            # SDL2 via Homebrew
            if ! brew list sdl2 &>/dev/null 2>&1; then
                log_error "SDL2 not found"
                echo ""
                echo "Install with: brew install sdl2"
                echo "Then re-run: ./setup.sh"
                exit 1
            fi
            # CoreMIDI is built-in on macOS, no check needed
            ;;
        windows)
            # Windows: SDL2 is bundled in tools/windows/, checked later in setup_sdl2_windows
            # WinMM is built-in
            ;;
    esac

    log_ok "System dependencies OK"
}

# =============================================================================
# Clone Repositories
# =============================================================================
clone_org_repos() {
    local org="$1"
    local target_dir="$2"
    
    log_info "Fetching repo list for $org..."
    
    local repos
    repos=$(gh repo list "$org" --limit 100 --json name --jq '.[].name')
    
    if [[ -z "$repos" ]]; then
        log_warn "No repos found for $org (or no access)"
        return
    fi
    
    mkdir -p "$target_dir"
    
    while IFS= read -r name; do
        local repo_path="$target_dir/$name"
        
        if [[ -d "$repo_path/.git" ]]; then
            log_ok "$org/$name (exists)"
        else
            log_info "Cloning $org/$name..."
            gh repo clone "$org/$name" "$repo_path" -- --quiet
            log_ok "$org/$name"
        fi
    done <<< "$repos"
}

clone_all_repos() {
    log_info "=== Cloning repositories ==="
    
    clone_org_repos "open-control" "$WORKSPACE/open-control"
    clone_org_repos "petitechose-midi-studio" "$WORKSPACE/midi-studio"
    
    log_ok "All repositories cloned"
}

# =============================================================================
# Download Utilities
# =============================================================================
get_github_latest_release() {
    local repo="$1"
    gh api "repos/$repo/releases/latest" --jq '.tag_name' 2>/dev/null | sed 's/^v//'
}

download_and_extract() {
    local url="$1"
    local dest="$2"
    local strip_components="${3:-1}"
    
    local temp_file
    temp_file=$(mktemp)
    
    log_info "Downloading $(basename "$url")..."
    curl -fsSL "$url" -o "$temp_file"
    
    mkdir -p "$dest"
    
    case "$url" in
        *.tar.gz|*.tgz)
            tar -xzf "$temp_file" -C "$dest" --strip-components="$strip_components"
            ;;
        *.tar.xz)
            tar -xJf "$temp_file" -C "$dest" --strip-components="$strip_components"
            ;;
        *.zip)
            local temp_dir
            temp_dir=$(mktemp -d)
            unzip -q "$temp_file" -d "$temp_dir"
            
            # Move contents (handle single directory or multiple files)
            local inner
            inner=$(find "$temp_dir" -mindepth 1 -maxdepth 1)
            local count
            count=$(echo "$inner" | wc -l)
            
            if [[ $count -eq 1 && -d "$inner" ]]; then
                mv "$inner"/* "$dest"/ 2>/dev/null || mv "$inner"/* "$dest"
            else
                mv "$temp_dir"/* "$dest"/
            fi
            rm -rf "$temp_dir"
            ;;
        *)
            log_error "Unknown archive format: $url"
            rm -f "$temp_file"
            return 1
            ;;
    esac
    
    rm -f "$temp_file"
}

# =============================================================================
# Install Tools (workspace-managed)
# =============================================================================

setup_tools_bin() {
    mkdir -p "$TOOLS_DIR/bin"
}

write_tools_wrapper() {
    local name="$1"
    local target_rel="$2"

    local wrapper="$TOOLS_DIR/bin/$name"
    cat >"$wrapper" <<EOF
#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="\$(cd "\$(dirname "\${BASH_SOURCE[0]}")" && pwd)"
TOOLS_DIR="\$(cd "\$SCRIPT_DIR/.." && pwd)"
exec "\$TOOLS_DIR/$target_rel" "\$@"
EOF
    chmod +x "$wrapper" 2>/dev/null || true
}

write_bunx_wrapper() {
    local wrapper="$TOOLS_DIR/bin/bunx"
    cat >"$wrapper" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TOOLS_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

BUN="$TOOLS_DIR/bun/bun"
if [[ -x "$TOOLS_DIR/bun/bun.exe" ]]; then
  BUN="$TOOLS_DIR/bun/bun.exe"
fi

exec "$BUN" x "$@"
EOF
    chmod +x "$wrapper" 2>/dev/null || true
}

setup_uv() {
    local uv_dir="$TOOLS_DIR/uv"
    local uv_bin="$uv_dir/uv"
    [[ "$OS" == "windows" ]] && uv_bin="$uv_dir/uv.exe"

    if [[ -x "$uv_bin" ]]; then
        local ver
        ver=$("$uv_bin" --version 2>/dev/null | awk '{print $2}')
        log_ok "uv $ver"
        return 0
    fi

    local version
    version=$(gh api "repos/astral-sh/uv/releases/latest" --jq '.tag_name')
    log_info "Installing uv $version..."

    local asset
    case "$OS-$ARCH" in
        linux-x64)   asset="uv-x86_64-unknown-linux-gnu.tar.gz" ;;
        linux-arm64) asset="uv-aarch64-unknown-linux-gnu.tar.gz" ;;
        macos-x64)   asset="uv-x86_64-apple-darwin.tar.gz" ;;
        macos-arm64) asset="uv-aarch64-apple-darwin.tar.gz" ;;
        windows-x64) asset="uv-x86_64-pc-windows-msvc.zip" ;;
        windows-arm64) asset="uv-aarch64-pc-windows-msvc.zip" ;;
        *)
            log_error "No uv build for $OS-$ARCH"
            return 1
            ;;
    esac

    local url="https://github.com/astral-sh/uv/releases/download/${version}/${asset}"
    download_and_extract "$url" "$uv_dir" 1

    chmod +x "$uv_dir/uv" "$uv_dir/uvx" 2>/dev/null || true

    # Expose via tools/bin
    if [[ "$OS" == "windows" ]]; then
        write_tools_wrapper "uv" "uv/uv.exe"
        write_tools_wrapper "uvx" "uv/uvx.exe"
    else
        write_tools_wrapper "uv" "uv/uv"
        write_tools_wrapper "uvx" "uv/uvx"
    fi

    log_ok "uv $version"
}

setup_python_venv() {
    # Unified workspace venv (Python 3.13+) managed by uv
    local venv_dir="$WORKSPACE/.venv"

    local python_bin="$venv_dir/bin/python"
    [[ "$OS" == "windows" ]] && python_bin="$venv_dir/Scripts/python.exe"

    if [[ -x "$python_bin" ]]; then
        local ver
        ver=$("$python_bin" -c 'import sys; print("%d.%d.%d" % sys.version_info[:3])' 2>/dev/null || true)
        [[ -n "$ver" ]] && log_ok "python $ver (.venv)"
        return 0
    fi

    local uv_bin="$TOOLS_DIR/uv/uv"
    [[ "$OS" == "windows" ]] && uv_bin="$TOOLS_DIR/uv/uv.exe"

    if [[ ! -x "$uv_bin" ]]; then
        log_error "uv not installed (cannot create .venv)"
        return 1
    fi

    local uv_python_dir="$TOOLS_DIR/python"

    log_info "Installing uv-managed Python 3.13 (if needed)..."
    UV_PYTHON_INSTALL_DIR="$uv_python_dir" "$uv_bin" python install 3.13 --managed-python

    log_info "Creating Python 3.13+ virtualenv (.venv)..."
    UV_PYTHON_INSTALL_DIR="$uv_python_dir" "$uv_bin" venv --managed-python --python 3.13 "$venv_dir"

    log_ok "python venv created"
}

setup_python_deps() {
    local uv_bin="$TOOLS_DIR/uv/uv"
    [[ "$OS" == "windows" ]] && uv_bin="$TOOLS_DIR/uv/uv.exe"

    if [[ ! -x "$uv_bin" ]]; then
        log_error "uv not installed (cannot sync python deps)"
        return 1
    fi

    if [[ ! -f "$WORKSPACE/pyproject.toml" ]]; then
        log_warn "pyproject.toml not found (skipping python deps)"
        return 0
    fi

    if [[ ! -f "$WORKSPACE/uv.lock" ]]; then
        log_warn "uv.lock not found (skipping python deps)"
        return 0
    fi

    log_info "Syncing Python deps (.venv)..."

    local uv_python_dir="$TOOLS_DIR/python"
    (
        cd "$WORKSPACE"
        UV_PYTHON_INSTALL_DIR="$uv_python_dir" "$uv_bin" sync --frozen
    )

    log_ok "python deps synced"
}

setup_bun() {
    local bun_dir="$TOOLS_DIR/bun"
    local bun_bin="$bun_dir/bun"
    [[ "$OS" == "windows" ]] && bun_bin="$bun_dir/bun.exe"

    if [[ -x "$bun_bin" ]]; then
        local ver
        ver=$("$bun_bin" --version 2>/dev/null || true)
        log_ok "bun $ver"
        return 0
    fi

    local tag
    tag=$(gh api "repos/oven-sh/bun/releases/latest" --jq '.tag_name')
    log_info "Installing bun $tag..."

    local asset
    case "$OS-$ARCH" in
        linux-x64)   asset="bun-linux-x64.zip" ;;
        linux-arm64) asset="bun-linux-aarch64.zip" ;;
        macos-x64)   asset="bun-darwin-x64.zip" ;;
        macos-arm64) asset="bun-darwin-aarch64.zip" ;;
        windows-x64) asset="bun-windows-x64.zip" ;;
        *)
            log_error "No bun build for $OS-$ARCH"
            return 1
            ;;
    esac

    local url="https://github.com/oven-sh/bun/releases/download/${tag}/${asset}"
    download_and_extract "$url" "$bun_dir" 0
    chmod +x "$bun_dir/bun" 2>/dev/null || true

    # Expose via tools/bin
    if [[ "$OS" == "windows" ]]; then
        write_tools_wrapper "bun" "bun/bun.exe"
    else
        write_tools_wrapper "bun" "bun/bun"
    fi
    write_bunx_wrapper

    log_ok "bun installed"
}

setup_jdk() {
    local jdk_dir="$TOOLS_DIR/jdk"

    local java_bin="$jdk_dir/bin/java"
    if [[ -x "$jdk_dir/Contents/Home/bin/java" ]]; then
        java_bin="$jdk_dir/Contents/Home/bin/java"
    fi

    if [[ -x "$java_bin" ]]; then
        local ver
        ver=$("$java_bin" -version 2>&1 | head -1 | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' || true)
        log_ok "jdk ${ver:-installed}"
        return 0
    fi

    log_info "Installing Temurin JDK 25 (LTS)..."

    local venv_python="$WORKSPACE/.venv/bin/python"
    [[ "$OS" == "windows" ]] && venv_python="$WORKSPACE/.venv/Scripts/python.exe"

    if [[ ! -x "$venv_python" ]]; then
        log_error "Python venv not found (cannot resolve JDK download)"
        log_error "Run: ./setup.sh"
        return 1
    fi

    local adoptium_os
    local adoptium_arch
    case "$OS" in
        linux) adoptium_os="linux" ;;
        macos) adoptium_os="mac" ;;
        windows) adoptium_os="windows" ;;
        *) log_error "Unsupported OS for JDK: $OS"; return 1 ;;
    esac

    case "$ARCH" in
        x64) adoptium_arch="x64" ;;
        arm64) adoptium_arch="aarch64" ;;
        *) log_error "Unsupported arch for JDK: $ARCH"; return 1 ;;
    esac

    local api_url="https://api.adoptium.net/v3/assets/latest/25/hotspot?architecture=${adoptium_arch}&image_type=jdk&os=${adoptium_os}"
    local final_url
    final_url=$(curl -fsSL "$api_url" | "$venv_python" -c 'import json,sys; d=json.load(sys.stdin); print(d[0]["binary"]["package"]["link"])')

    if [[ -z "$final_url" ]]; then
        log_error "Could not resolve JDK download URL"
        return 1
    fi

    download_and_extract "$final_url" "$jdk_dir" 1

    # Expose via tools/bin (java + javac)
    cat >"$TOOLS_DIR/bin/java" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TOOLS_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

JAVA_HOME="$TOOLS_DIR/jdk"
if [[ -x "$JAVA_HOME/Contents/Home/bin/java" ]]; then
  JAVA_HOME="$JAVA_HOME/Contents/Home"
fi

exec "$JAVA_HOME/bin/java" "$@"
EOF
    chmod +x "$TOOLS_DIR/bin/java" 2>/dev/null || true

    cat >"$TOOLS_DIR/bin/javac" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TOOLS_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

JAVA_HOME="$TOOLS_DIR/jdk"
if [[ -x "$JAVA_HOME/Contents/Home/bin/javac" ]]; then
  JAVA_HOME="$JAVA_HOME/Contents/Home"
fi

exec "$JAVA_HOME/bin/javac" "$@"
EOF
    chmod +x "$TOOLS_DIR/bin/javac" 2>/dev/null || true

    log_ok "jdk installed"
}

setup_maven() {
    local maven_dir="$TOOLS_DIR/maven"

    if [[ -x "$maven_dir/bin/mvn" ]]; then
        log_ok "maven installed"
        return 0
    fi

    log_info "Resolving latest Maven 3.9.x..."
    local meta
    meta=$(curl -fsSL "https://repo1.maven.org/maven2/org/apache/maven/apache-maven/maven-metadata.xml")

    local version
    version=$(echo "$meta" | grep -oE '<version>3\.9\.[0-9]+</version>' | sed 's/[^0-9.]//g' | sort -V | tail -1)

    if [[ -z "$version" ]]; then
        log_error "Could not determine Maven 3.9.x version"
        return 1
    fi

    log_info "Installing Maven $version..."

    local url_primary="https://dlcdn.apache.org/maven/maven-3/${version}/binaries/apache-maven-${version}-bin.tar.gz"
    local url_fallback="https://archive.apache.org/dist/maven/maven-3/${version}/binaries/apache-maven-${version}-bin.tar.gz"

    if curl -fsSL -o /dev/null "$url_primary"; then
        download_and_extract "$url_primary" "$maven_dir" 1
    else
        download_and_extract "$url_fallback" "$maven_dir" 1
    fi

    write_tools_wrapper "mvn" "maven/bin/mvn"
    log_ok "maven $version"
}

setup_platformio() {
    # PlatformIO installer script (recommended by PlatformIO).
    # Installs into ~/.platformio/penv and provides `pio` there.
    local pio_home="$HOME/.platformio"
    local pio_bin_unix="$pio_home/penv/bin/pio"
    local pio_bin_win="$pio_home/penv/Scripts/pio.exe"

    # Always provide a stable wrapper via tools/bin, even if PlatformIO was
    # installed previously.
    mkdir -p "$TOOLS_DIR/bin"
    cat >"$TOOLS_DIR/bin/pio" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail

PIO_UNIX="$HOME/.platformio/penv/bin/pio"
PIO_WIN="$HOME/.platformio/penv/Scripts/pio.exe"

if [[ -x "$PIO_UNIX" ]]; then
  exec "$PIO_UNIX" "$@"
fi
if [[ -x "$PIO_WIN" ]]; then
  exec "$PIO_WIN" "$@"
fi

echo "error: platformio is not installed" >&2
echo "install: run ./setup.sh or see PlatformIO docs" >&2
exit 1
EOF
    chmod +x "$TOOLS_DIR/bin/pio" 2>/dev/null || true

    if [[ -x "$pio_bin_unix" ]] || [[ -x "$pio_bin_win" ]]; then
        log_ok "platformio $("$TOOLS_DIR/bin/pio" --version 2>/dev/null | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1)"
        return 0
    fi

    local venv_python="$WORKSPACE/.venv/bin/python"
    [[ "$OS" == "windows" ]] && venv_python="$WORKSPACE/.venv/Scripts/python.exe"

    if [[ ! -x "$venv_python" ]]; then
        log_error "Python venv not found (cannot install PlatformIO)"
        log_error "Run: ./setup.sh"
        return 1
    fi

    log_info "Installing PlatformIO Core (installer script)..."

    local tmp
    tmp=$(mktemp)
    curl -fsSL "https://raw.githubusercontent.com/platformio/platformio-core-installer/master/get-platformio.py" -o "$tmp"
    "$venv_python" "$tmp"
    rm -f "$tmp"

    log_ok "platformio $("$TOOLS_DIR/bin/pio" --version 2>/dev/null | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1)"
}
setup_cmake() {
    local cmake_dir="$TOOLS_DIR/cmake"
    
    if [[ -x "$cmake_dir/bin/cmake" ]] || [[ -x "$cmake_dir/bin/cmake.exe" ]]; then
        local ver=$("$cmake_dir/bin/cmake" --version 2>/dev/null | head -1 | grep -oE '[0-9]+\.[0-9]+\.[0-9]+')
        if [[ "$OS" == "windows" ]]; then
            write_tools_wrapper "cmake" "cmake/bin/cmake.exe"
        else
            write_tools_wrapper "cmake" "cmake/bin/cmake"
        fi
        log_ok "cmake $ver"
        return 0
    fi
    
    local version
    version=$(get_github_latest_release "Kitware/CMake")
    log_info "Installing cmake $version..."
    
    local url
    case "$OS-$ARCH" in
        linux-x64)   url="https://github.com/Kitware/CMake/releases/download/v${version}/cmake-${version}-linux-x86_64.tar.gz" ;;
        linux-arm64) url="https://github.com/Kitware/CMake/releases/download/v${version}/cmake-${version}-linux-aarch64.tar.gz" ;;
        macos-*)     url="https://github.com/Kitware/CMake/releases/download/v${version}/cmake-${version}-macos-universal.tar.gz" ;;
        windows-*)   url="https://github.com/Kitware/CMake/releases/download/v${version}/cmake-${version}-windows-x86_64.zip" ;;
    esac
    
    download_and_extract "$url" "$cmake_dir"
    
    # macOS: extract from CMake.app bundle
    if [[ "$OS" == "macos" && -d "$cmake_dir/CMake.app" ]]; then
        mv "$cmake_dir/CMake.app/Contents"/* "$cmake_dir"/
        rm -rf "$cmake_dir/CMake.app"
    fi

    if [[ "$OS" == "windows" ]]; then
        write_tools_wrapper "cmake" "cmake/bin/cmake.exe"
    else
        write_tools_wrapper "cmake" "cmake/bin/cmake"
    fi
    
    log_ok "cmake $version"
}

setup_ninja() {
    local ninja_dir="$TOOLS_DIR/ninja"
    local ninja_bin="$ninja_dir/ninja"
    [[ "$OS" == "windows" ]] && ninja_bin="$ninja_dir/ninja.exe"
    
    if [[ -x "$ninja_bin" ]]; then
        if [[ "$OS" == "windows" ]]; then
            write_tools_wrapper "ninja" "ninja/ninja.exe"
        else
            write_tools_wrapper "ninja" "ninja/ninja"
        fi
        log_ok "ninja"
        return 0
    fi
    
    local version
    version=$(get_github_latest_release "ninja-build/ninja")
    log_info "Installing ninja $version..."
    
    local url
    case "$OS-$ARCH" in
        linux-x64)   url="https://github.com/ninja-build/ninja/releases/download/v${version}/ninja-linux.zip" ;;
        linux-arm64) url="https://github.com/ninja-build/ninja/releases/download/v${version}/ninja-linux-aarch64.zip" ;;
        macos-*)     url="https://github.com/ninja-build/ninja/releases/download/v${version}/ninja-mac.zip" ;;
        windows-*)   url="https://github.com/ninja-build/ninja/releases/download/v${version}/ninja-win.zip" ;;
    esac
    
    download_and_extract "$url" "$ninja_dir" 0
    chmod +x "$ninja_dir/ninja" 2>/dev/null || true

    if [[ "$OS" == "windows" ]]; then
        write_tools_wrapper "ninja" "ninja/ninja.exe"
    else
        write_tools_wrapper "ninja" "ninja/ninja"
    fi
    
    log_ok "ninja $version"
}

setup_zig() {
    local zig_dir="$TOOLS_DIR/zig"
    local zig_bin="$zig_dir/zig"
    [[ "$OS" == "windows" ]] && zig_bin="$zig_dir/zig.exe"
    
    if [[ -x "$zig_bin" ]]; then
        local ver=$("$zig_bin" version 2>/dev/null)
        if [[ "$ver" == *"-dev."* || "$ver" == *"-dev"* ]]; then
            log_warn "zig $ver detected (dev build) - reinstalling latest stable"
            rm -rf "$zig_dir"
        else
            if [[ "$OS" == "windows" ]]; then
                write_tools_wrapper "zig" "zig/zig.exe"
            else
                write_tools_wrapper "zig" "zig/zig"
            fi
            log_ok "zig $ver"
            return 0
        fi
    fi
    
    log_info "Installing zig (latest stable)..."

    local venv_python="$WORKSPACE/.venv/bin/python"
    [[ "$OS" == "windows" ]] && venv_python="$WORKSPACE/.venv/Scripts/python.exe"

    if [[ ! -x "$venv_python" ]]; then
        log_error "Python venv not found (cannot resolve Zig download)"
        log_error "Run: ./setup.sh"
        return 1
    fi

    local zig_platform=""
    case "$OS-$ARCH" in
        linux-x64)    zig_platform="x86_64-linux" ;;
        linux-arm64)  zig_platform="aarch64-linux" ;;
        macos-x64)    zig_platform="x86_64-macos" ;;
        macos-arm64)  zig_platform="aarch64-macos" ;;
        windows-x64)  zig_platform="x86_64-windows" ;;
        windows-arm64) zig_platform="aarch64-windows" ;;
    esac

    if [[ -z "$zig_platform" ]]; then
        log_error "Unsupported platform for Zig: $OS-$ARCH"
        return 1
    fi

    local resolved
    resolved=$(curl -fsSL "https://ziglang.org/download/index.json" | "$venv_python" -c 'import json,re,sys; data=json.load(sys.stdin); platform=sys.argv[1]; stable=[k for k in data.keys() if re.fullmatch(r"\d+\.\d+\.\d+", k)]; stable.sort(key=lambda s: tuple(map(int, s.split(".")))); assert stable, "no stable Zig versions found"; v=stable[-1]; print(v + "|" + data[v][platform]["tarball"])' "$zig_platform")

    local version="${resolved%%|*}"
    local url="${resolved#*|}"

    if [[ -z "$version" || -z "$url" ]]; then
        log_error "Could not resolve Zig download URL"
        return 1
    fi

    download_and_extract "$url" "$zig_dir"

    if [[ "$OS" == "windows" ]]; then
        write_tools_wrapper "zig" "zig/zig.exe"
    else
        write_tools_wrapper "zig" "zig/zig"
    fi

    log_ok "zig $version"
}

setup_sdl2_windows() {
    # Windows only - Linux/macOS use system packages (checked in check_system_deps)
    if [[ "$OS" != "windows" ]]; then
        return 0
    fi

    local sdl_dir="$TOOLS_DIR/windows/SDL2"

    if [[ -f "$sdl_dir/lib/libSDL2.a" ]] || [[ -f "$sdl_dir/lib/libSDL2.dll.a" ]]; then
        local ver=$(grep "^Version:" "$sdl_dir/lib/pkgconfig/sdl2.pc" 2>/dev/null | cut -d' ' -f2 || echo "installed")
        log_ok "SDL2 $ver (bundled)"
        return 0
    fi

    # Get latest SDL2 version (not SDL3)
    local version
    version=$(gh api "repos/libsdl-org/SDL/releases" --jq '[.[] | select(.tag_name | startswith("release-2"))][0].tag_name' | sed 's/release-//')

    if [[ -z "$version" ]]; then
        log_error "Could not determine SDL2 version"
        return 1
    fi

    log_info "Installing SDL2 $version for Windows..."

    local url="https://github.com/libsdl-org/SDL/releases/download/release-${version}/SDL2-devel-${version}-mingw.tar.gz"
    mkdir -p "$TOOLS_DIR/windows"
    download_and_extract "$url" "$sdl_dir"

    # Move x86_64-w64-mingw32 contents to root
    if [[ -d "$sdl_dir/SDL2-${version}/x86_64-w64-mingw32" ]]; then
        mv "$sdl_dir/SDL2-${version}/x86_64-w64-mingw32"/* "$sdl_dir"/
        rm -rf "$sdl_dir/SDL2-${version}"
    fi

    log_ok "SDL2 $version (bundled)"
}

setup_emscripten() {
    local emsdk_dir="$TOOLS_DIR/emsdk"
    
    if [[ -f "$emsdk_dir/upstream/emscripten/emcc" ]] || [[ -f "$emsdk_dir/upstream/emscripten/emcc.bat" ]]; then
        log_ok "emscripten"
        return 0
    fi
    
    log_info "Installing Emscripten SDK (this may take a while)..."
    
    if [[ ! -d "$emsdk_dir" ]]; then
        git clone --quiet https://github.com/emscripten-core/emsdk.git "$emsdk_dir"
    fi
    
    local venv_python="$WORKSPACE/.venv/bin/python"
    [[ "$OS" == "windows" ]] && venv_python="$WORKSPACE/.venv/Scripts/python.exe"

    if [[ ! -x "$venv_python" ]]; then
        log_error "Python venv not found (cannot install emsdk)"
        log_error "Run: ./setup.sh"
        return 1
    fi

    (
        cd "$emsdk_dir"
        "$venv_python" "$emsdk_dir/emsdk.py" install latest
        "$venv_python" "$emsdk_dir/emsdk.py" activate latest
    )
    
    log_ok "emscripten (latest)"
}

install_tools() {
    log_info "=== Installing build tools (portable) ==="

    mkdir -p "$TOOLS_DIR"

    setup_tools_bin

    setup_uv
    setup_python_venv
    setup_python_deps

    setup_cmake
    setup_ninja
    setup_zig
    setup_bun
    setup_jdk
    setup_maven
    setup_sdl2_windows  # Windows only - Linux/macOS use system packages
    setup_emscripten

    setup_platformio

    log_ok "All tools installed in $TOOLS_DIR"
}

# =============================================================================
# Configure Shell
# =============================================================================
configure_shell() {
    log_info "=== Configuring shell environment ==="
    
    # Detect shell config file
    local shell_config=""
    case "$(basename "${SHELL:-bash}")" in
        zsh)  shell_config="$HOME/.zshrc" ;;
        bash)
            if [[ "$OS" == "macos" ]]; then
                shell_config="$HOME/.bash_profile"
            else
                shell_config="$HOME/.bashrc"
            fi
            ;;
        *)    shell_config="$HOME/.profile" ;;
    esac
    
    local marker_start="# >>> petitechose-audio workspace >>>"
    local marker_end="# <<< petitechose-audio workspace <<<"

    if grep -qF "$marker_start" "$shell_config" 2>/dev/null; then
        log_ok "Shell already configured in $shell_config"
        return 0
    fi

    local config_block="
$marker_start
export WORKSPACE_ROOT=\"$WORKSPACE\"
export WORKSPACE_TOOLS=\"\$WORKSPACE_ROOT/tools\"
export ZIG_DIR=\"\$WORKSPACE_TOOLS/zig\"
export SDL2_ROOT=\"\$WORKSPACE_TOOLS/windows/SDL2\"  # Windows only, Linux/macOS use system SDL2

# Java
if [[ -d \"\$WORKSPACE_TOOLS/jdk/Contents/Home\" ]]; then
  export JAVA_HOME=\"\$WORKSPACE_TOOLS/jdk/Contents/Home\"
else
  export JAVA_HOME=\"\$WORKSPACE_TOOLS/jdk\"
fi

# Add tools to PATH
export PATH=\"\$WORKSPACE_TOOLS/bin:\$PATH\"
export PATH=\"\$WORKSPACE_ROOT/commands:\$PATH\"
export PATH=\"\$WORKSPACE_ROOT/open-control/cli-tools/bin:\$PATH\"
export PATH=\"\$JAVA_HOME/bin:\$PATH\"

# Emscripten (source if exists)
[[ -f \"\$WORKSPACE_TOOLS/emsdk/emsdk_env.sh\" ]] && source \"\$WORKSPACE_TOOLS/emsdk/emsdk_env.sh\" 2>/dev/null

# ms completions
if [[ -n "${ZSH_VERSION:-}" && -f \"\$WORKSPACE_ROOT/commands/_ms_completions.zsh\" ]]; then
  source \"\$WORKSPACE_ROOT/commands/_ms_completions.zsh\" 2>/dev/null
else
  [[ -f \"\$WORKSPACE_ROOT/commands/_ms_completions.bash\" ]] && source \"\$WORKSPACE_ROOT/commands/_ms_completions.bash\" 2>/dev/null
fi
$marker_end
"

    if [[ $INTERACTIVE -eq 1 ]]; then
        echo ""
        echo "The following will be added to $shell_config:"
        echo "$config_block"
        echo ""
        read -p "Add automatically? [Y/n] " yn
        if [[ "$yn" == "n" || "$yn" == "N" ]]; then
            log_warn "Skipped. Add manually to your shell config."
            return 0
        fi
    fi
    
    echo "$config_block" >> "$shell_config"
    log_ok "Shell configured in $shell_config"
    log_warn "Run: source $shell_config (or restart terminal)"
}

verify_installation() {
    log_info "=== Verifying installation ==="

    local missing=0
    local check_path="$TOOLS_DIR/bin:$PATH"

    for tool in cmake ninja zig uv bun java javac mvn pio; do
        if ! PATH="$check_path" command -v "$tool" &>/dev/null; then
            log_warn "missing: $tool"
            missing=1
        fi
    done

    if [[ $missing -eq 0 ]]; then
        log_ok "Tooling looks OK"
    else
        log_warn "Some tools are missing from PATH (restart shell after setup)"
    fi
}

# =============================================================================
# Main
# =============================================================================
main() {
    echo ""
    echo "============================================"
    echo " MIDI Studio - Development Environment Setup"
    echo " Mode: 100% Portable"
    echo "============================================"
    echo ""
    
    local skip_tools=0
    local skip_repos=0
    local skip_shell=0
    
    for arg in "$@"; do
        case "$arg" in
            --skip-tools) skip_tools=1 ;;
            --skip-repos) skip_repos=1 ;;
            --skip-shell) skip_shell=1 ;;
            --help|-h)
                echo "Usage: ./setup.sh [--skip-tools] [--skip-repos] [--skip-shell]"
                echo ""
                echo "Installs all build tools in workspace/tools/ (portable, no sudo needed)"
                exit 0
                ;;
        esac
    done
    
    detect_platform
    check_prerequisites
    check_system_deps

    echo ""

    if [[ $skip_repos -eq 0 ]]; then
        clone_all_repos
        echo ""
    fi
    
    if [[ $skip_tools -eq 0 ]]; then
        install_tools
        echo ""
    fi
    
    if [[ $skip_shell -eq 0 ]]; then
        configure_shell
        echo ""
    else
        log_warn "Skipping shell configuration (--skip-shell)"
    fi

    verify_installation
    
    echo ""
    echo "============================================"
    log_ok "Setup complete!"
    echo ""
    echo "Next steps:"
    echo "  1. Restart terminal (or: source ~/.bashrc)"
    echo "  2. Doctor: ms doctor"
    echo "  3. Verify: ms verify"
    echo "============================================"
}

main "$@"
