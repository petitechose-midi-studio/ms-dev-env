#!/usr/bin/env bash
# =============================================================================
# MIDI Studio / Open Control - Development Environment Setup
# =============================================================================
# Clone all repos + install all build tools (100% portable)
#
# Usage: ./setup.sh [--skip-tools] [--skip-repos]
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
# Prerequisites Check (minimal - just git, gh, python)
# =============================================================================
check_prerequisites() {
    log_info "Checking prerequisites..."
    local failed=0

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

    # Python (needed for emsdk)
    if ! command -v python3 &>/dev/null && ! command -v python &>/dev/null; then
        log_error "python not found"
        echo "  Linux:   sudo apt install python3"
        echo "  macOS:   brew install python3"
        echo "  Windows: winget install Python.Python.3.11"
        failed=1
    fi

    if [[ $failed -eq 1 ]]; then
        exit 1
    fi

    log_ok "Prerequisites OK"
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
# Install Tools (100% Portable)
# =============================================================================
setup_cmake() {
    local cmake_dir="$TOOLS_DIR/cmake"
    
    if [[ -x "$cmake_dir/bin/cmake" ]] || [[ -x "$cmake_dir/bin/cmake.exe" ]]; then
        local ver=$("$cmake_dir/bin/cmake" --version 2>/dev/null | head -1 | grep -oE '[0-9]+\.[0-9]+\.[0-9]+')
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
    
    log_ok "cmake $version"
}

setup_ninja() {
    local ninja_dir="$TOOLS_DIR/ninja"
    local ninja_bin="$ninja_dir/ninja"
    [[ "$OS" == "windows" ]] && ninja_bin="$ninja_dir/ninja.exe"
    
    if [[ -x "$ninja_bin" ]]; then
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
    
    log_ok "ninja $version"
}

setup_zig() {
    local zig_dir="$TOOLS_DIR/zig"
    local zig_bin="$zig_dir/zig"
    [[ "$OS" == "windows" ]] && zig_bin="$zig_dir/zig.exe"
    
    if [[ -x "$zig_bin" ]]; then
        local ver=$("$zig_bin" version 2>/dev/null)
        log_ok "zig $ver"
        return 0
    fi
    
    # Get latest Zig version from ziglang.org
    log_info "Installing zig..."
    
    local index_json
    index_json=$(curl -fsSL "https://ziglang.org/download/index.json")
    
    local version
    version=$(echo "$index_json" | grep -oE '"[0-9]+\.[0-9]+\.[0-9]+"' | head -1 | tr -d '"')
    
    local url
    case "$OS-$ARCH" in
        linux-x64)   url=$(echo "$index_json" | grep -oE 'https://[^"]+x86_64-linux[^"]+\.tar\.xz' | head -1) ;;
        linux-arm64) url=$(echo "$index_json" | grep -oE 'https://[^"]+aarch64-linux[^"]+\.tar\.xz' | head -1) ;;
        macos-x64)   url=$(echo "$index_json" | grep -oE 'https://[^"]+x86_64-macos[^"]+\.tar\.xz' | head -1) ;;
        macos-arm64) url=$(echo "$index_json" | grep -oE 'https://[^"]+aarch64-macos[^"]+\.tar\.xz' | head -1) ;;
        windows-*)   url=$(echo "$index_json" | grep -oE 'https://[^"]+x86_64-windows[^"]+\.zip' | head -1) ;;
    esac
    
    if [[ -z "$url" ]]; then
        log_error "Could not find Zig download for $OS-$ARCH"
        return 1
    fi
    
    download_and_extract "$url" "$zig_dir"
    
    log_ok "zig $version"
}

setup_sdl2() {
    local sdl_dir="$TOOLS_DIR/SDL2"
    
    if [[ -f "$sdl_dir/lib/libSDL2.a" ]] || [[ -f "$sdl_dir/lib/libSDL2.dll.a" ]]; then
        local ver=$(grep "^Version:" "$sdl_dir/lib/pkgconfig/sdl2.pc" 2>/dev/null | cut -d' ' -f2 || echo "installed")
        log_ok "SDL2 $ver"
        return 0
    fi
    
    # Get latest SDL2 version (not SDL3)
    local version
    version=$(gh api "repos/libsdl-org/SDL/releases" --jq '[.[] | select(.tag_name | startswith("release-2"))][0].tag_name' | sed 's/release-//')
    
    if [[ -z "$version" ]]; then
        log_error "Could not determine SDL2 version"
        return 1
    fi
    
    log_info "Installing SDL2 $version..."
    
    local url
    case "$OS" in
        linux)
            # Linux: download source and extract prebuilt or use dev package structure
            url="https://github.com/libsdl-org/SDL/releases/download/release-${version}/SDL2-devel-${version}-mingw.tar.gz"
            download_and_extract "$url" "$sdl_dir"
            # Use x86_64 mingw build
            if [[ -d "$sdl_dir/SDL2-${version}/x86_64-w64-mingw32" ]]; then
                # Actually for Linux we need different approach - download source
                rm -rf "$sdl_dir"
                mkdir -p "$sdl_dir"
                log_warn "SDL2 on Linux: downloading source..."
                local src_url="https://github.com/libsdl-org/SDL/releases/download/release-${version}/SDL2-${version}.tar.gz"
                download_and_extract "$src_url" "$sdl_dir"
                log_warn "SDL2 needs to be compiled. Run: cd $sdl_dir && ./configure && make"
                log_warn "Or install via package manager: sudo apt install libsdl2-dev"
            fi
            ;;
        macos)
            url="https://github.com/libsdl-org/SDL/releases/download/release-${version}/SDL2-${version}.dmg"
            log_warn "SDL2 on macOS: install via Homebrew is easier"
            log_warn "  brew install sdl2"
            log_warn "Or download from: $url"
            return 0
            ;;
        windows)
            url="https://github.com/libsdl-org/SDL/releases/download/release-${version}/SDL2-devel-${version}-mingw.tar.gz"
            download_and_extract "$url" "$sdl_dir"
            # Move x86_64-w64-mingw32 contents to root
            if [[ -d "$sdl_dir/SDL2-${version}/x86_64-w64-mingw32" ]]; then
                mv "$sdl_dir/SDL2-${version}/x86_64-w64-mingw32"/* "$sdl_dir"/
                rm -rf "$sdl_dir/SDL2-${version}"
            fi
            ;;
    esac
    
    log_ok "SDL2 $version"
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
    
    cd "$emsdk_dir"
    ./emsdk install latest
    ./emsdk activate latest
    cd "$WORKSPACE"
    
    log_ok "emscripten (latest)"
}

install_tools() {
    log_info "=== Installing build tools (portable) ==="
    
    mkdir -p "$TOOLS_DIR"
    
    setup_cmake
    setup_ninja
    setup_zig
    setup_sdl2
    setup_emscripten
    
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
    
    # Check if already configured
    if grep -q "WORKSPACE_TOOLS" "$shell_config" 2>/dev/null; then
        log_ok "Shell already configured in $shell_config"
        return 0
    fi
    
    local config_block="
# =============================================================================
# petitechose-audio development environment
# =============================================================================
export WORKSPACE_ROOT=\"$WORKSPACE\"
export WORKSPACE_TOOLS=\"\$WORKSPACE_ROOT/tools\"
export ZIG_DIR=\"\$WORKSPACE_TOOLS/zig\"
export SDL2_ROOT=\"\$WORKSPACE_TOOLS/SDL2\"

# Add tools to PATH
export PATH=\"\$WORKSPACE_TOOLS/cmake/bin:\$PATH\"
export PATH=\"\$WORKSPACE_TOOLS/ninja:\$PATH\"
export PATH=\"\$WORKSPACE_TOOLS/zig:\$PATH\"
export PATH=\"\$WORKSPACE_ROOT/commands:\$PATH\"
export PATH=\"\$WORKSPACE_ROOT/open-control/cli-tools/bin:\$PATH\"

# Emscripten (source if exists)
[[ -f \"\$WORKSPACE_TOOLS/emsdk/emsdk_env.sh\" ]] && source \"\$WORKSPACE_TOOLS/emsdk/emsdk_env.sh\" 2>/dev/null
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

# =============================================================================
# Optional: PlatformIO, Rust
# =============================================================================
setup_optional() {
    log_info "=== Optional tools ==="
    
    # Rust
    if command -v cargo &>/dev/null; then
        log_ok "rust $(cargo --version | cut -d' ' -f2)"
    elif [[ $INTERACTIVE -eq 1 ]]; then
        echo ""
        read -p "Install Rust? (needed for oc-bridge) [y/N] " yn
        if [[ "$yn" == "y" || "$yn" == "Y" ]]; then
            curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
            log_ok "rust installed"
        fi
    else
        log_warn "rust not found (install: curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh)"
    fi
    
    # PlatformIO
    if command -v pio &>/dev/null; then
        log_ok "platformio $(pio --version 2>/dev/null | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1)"
    elif [[ $INTERACTIVE -eq 1 ]]; then
        echo ""
        read -p "Install PlatformIO? (needed for Teensy builds) [y/N] " yn
        if [[ "$yn" == "y" || "$yn" == "Y" ]]; then
            pip3 install platformio || pip install platformio
            log_ok "platformio installed"
        fi
    else
        log_warn "platformio not found (install: pip install platformio)"
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
    
    for arg in "$@"; do
        case "$arg" in
            --skip-tools) skip_tools=1 ;;
            --skip-repos) skip_repos=1 ;;
            --help|-h)
                echo "Usage: ./setup.sh [--skip-tools] [--skip-repos]"
                echo ""
                echo "Installs all build tools in workspace/tools/ (portable, no sudo needed)"
                exit 0
                ;;
        esac
    done
    
    detect_platform
    check_prerequisites
    
    echo ""
    
    if [[ $skip_repos -eq 0 ]]; then
        clone_all_repos
        echo ""
    fi
    
    if [[ $skip_tools -eq 0 ]]; then
        install_tools
        echo ""
    fi
    
    configure_shell
    echo ""
    
    setup_optional
    
    echo ""
    echo "============================================"
    log_ok "Setup complete!"
    echo ""
    echo "Next steps:"
    echo "  1. Restart terminal (or: source ~/.bashrc)"
    echo "  2. Test: ms help"
    echo "  3. Build: ms run core"
    echo "============================================"
}

main "$@"
