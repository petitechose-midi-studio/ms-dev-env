#!/usr/bin/env bash
# =============================================================================
# MIDI Studio / Open Control - Development Environment Setup
# =============================================================================
# Clone all repos + install shared build tools
#
# Usage: ./setup.sh [--skip-tools] [--skip-repos]
# =============================================================================

set -euo pipefail

WORKSPACE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TOOLS_DIR="$WORKSPACE/tools"

# Colors (if terminal supports it)
if [[ -t 1 ]]; then
    RED='\033[0;31m'
    GREEN='\033[0;32m'
    YELLOW='\033[0;33m'
    BLUE='\033[0;34m'
    NC='\033[0m' # No Color
else
    RED='' GREEN='' YELLOW='' BLUE='' NC=''
fi

log_info()  { echo -e "${BLUE}[INFO]${NC} $*"; }
log_ok()    { echo -e "${GREEN}[OK]${NC} $*"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }
log_error() { echo -e "${RED}[ERROR]${NC} $*"; }

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
# Prerequisites Check
# =============================================================================

check_prerequisite() {
    local cmd="$1"
    local install_hint="$2"
    
    if command -v "$cmd" &>/dev/null; then
        return 0
    else
        log_error "$cmd not found"
        echo ""
        echo "Install $cmd first:"
        echo "$install_hint"
        echo ""
        return 1
    fi
}

check_prerequisites() {
    log_info "Checking prerequisites..."
    local failed=0

    # Git
    if ! check_prerequisite "git" "$(cat <<EOF
  Linux:   sudo apt install git
  macOS:   xcode-select --install
  Windows: winget install Git.Git
EOF
)"; then failed=1; fi

    # GitHub CLI
    if ! check_prerequisite "gh" "$(cat <<EOF
  Linux:   sudo apt install gh  OR  https://cli.github.com/
  macOS:   brew install gh
  Windows: winget install GitHub.cli
EOF
)"; then failed=1; fi

    # Python
    if ! command -v python3 &>/dev/null && ! command -v python &>/dev/null; then
        log_error "python not found"
        echo ""
        echo "Install python first:"
        echo "  Linux:   sudo apt install python3"
        echo "  macOS:   brew install python3"
        echo "  Windows: winget install Python.Python.3.11"
        echo ""
        failed=1
    fi

    # C/C++ Compiler
    if ! command -v gcc &>/dev/null && ! command -v clang &>/dev/null; then
        log_error "C/C++ compiler not found"
        echo ""
        echo "Install a compiler:"
        echo "  Linux:   sudo apt install build-essential"
        echo "  macOS:   xcode-select --install"
        echo "  Windows: Install MSYS2 with mingw-w64"
        echo ""
        failed=1
    fi

    # Check gh is authenticated
    if command -v gh &>/dev/null; then
        if ! gh auth status &>/dev/null; then
            log_error "GitHub CLI not authenticated"
            echo ""
            echo "Run: gh auth login"
            echo ""
            failed=1
        fi
    fi

    if [[ $failed -eq 1 ]]; then
        exit 1
    fi

    log_ok "All prerequisites met"
}

# =============================================================================
# Clone Repositories
# =============================================================================

clone_org_repos() {
    local org="$1"
    local target_dir="$2"
    
    log_info "Fetching repo list for $org..."
    
    local repos
    repos=$(gh repo list "$org" --limit 100 --json name,url --jq '.[] | "\(.name) \(.url)"')
    
    if [[ -z "$repos" ]]; then
        log_warn "No repos found for $org (or no access)"
        return
    fi
    
    mkdir -p "$target_dir"
    
    while IFS=' ' read -r name url; do
        local repo_path="$target_dir/$name"
        
        if [[ -d "$repo_path/.git" ]]; then
            log_ok "$target_dir/$name (exists)"
        else
            log_info "Cloning $org/$name..."
            gh repo clone "$org/$name" "$repo_path" -- --quiet
            log_ok "$target_dir/$name"
        fi
    done <<< "$repos"
}

clone_all_repos() {
    log_info "=== Cloning repositories ==="
    
    clone_org_repos "open-control" "$WORKSPACE/open-control"
    clone_org_repos "petitechose-midi-studio" "$WORKSPACE/midi-studio"
    
    echo ""
    log_ok "All repositories cloned"
}

# =============================================================================
# Install Shared Tools
# =============================================================================

get_github_latest_release() {
    local repo="$1"
    gh api "repos/$repo/releases/latest" --jq '.tag_name' 2>/dev/null | sed 's/^v//'
}

download_and_extract() {
    local url="$1"
    local dest="$2"
    local temp_file
    
    temp_file=$(mktemp)
    
    log_info "Downloading $(basename "$url")..."
    curl -fsSL "$url" -o "$temp_file"
    
    mkdir -p "$dest"
    
    case "$url" in
        *.tar.gz|*.tgz)
            tar -xzf "$temp_file" -C "$dest" --strip-components=1
            ;;
        *.zip)
            if command -v unzip &>/dev/null; then
                unzip -q "$temp_file" -d "$dest"
                # Handle single-directory archives
                local inner_dir
                inner_dir=$(find "$dest" -mindepth 1 -maxdepth 1 -type d | head -1)
                if [[ -n "$inner_dir" && "$inner_dir" != "$dest" ]]; then
                    mv "$inner_dir"/* "$dest"/ 2>/dev/null || true
                    rmdir "$inner_dir" 2>/dev/null || true
                fi
            else
                log_error "unzip not found, cannot extract $url"
                rm -f "$temp_file"
                return 1
            fi
            ;;
        *)
            log_error "Unknown archive format: $url"
            rm -f "$temp_file"
            return 1
            ;;
    esac
    
    rm -f "$temp_file"
}

setup_cmake() {
    local cmake_dir="$TOOLS_DIR/cmake"
    
    if [[ -x "$cmake_dir/bin/cmake" ]]; then
        log_ok "cmake ($("$cmake_dir/bin/cmake" --version | head -1 | cut -d' ' -f3))"
        return 0
    fi
    
    # Also accept system cmake
    if command -v cmake &>/dev/null; then
        log_ok "cmake ($(cmake --version | head -1 | cut -d' ' -f3)) [system]"
        return 0
    fi
    
    local version
    version=$(get_github_latest_release "Kitware/CMake")
    log_info "Installing cmake $version..."
    
    local url
    case "$OS-$ARCH" in
        linux-x64)  url="https://github.com/Kitware/CMake/releases/download/v${version}/cmake-${version}-linux-x86_64.tar.gz" ;;
        linux-arm64) url="https://github.com/Kitware/CMake/releases/download/v${version}/cmake-${version}-linux-aarch64.tar.gz" ;;
        macos-*)    url="https://github.com/Kitware/CMake/releases/download/v${version}/cmake-${version}-macos-universal.tar.gz" ;;
        windows-*)  url="https://github.com/Kitware/CMake/releases/download/v${version}/cmake-${version}-windows-x86_64.zip" ;;
    esac
    
    download_and_extract "$url" "$cmake_dir"
    log_ok "cmake $version"
}

setup_ninja() {
    local ninja_dir="$TOOLS_DIR/ninja"
    
    if [[ -x "$ninja_dir/ninja" ]] || [[ -x "$ninja_dir/ninja.exe" ]]; then
        log_ok "ninja"
        return 0
    fi
    
    if command -v ninja &>/dev/null; then
        log_ok "ninja ($(ninja --version)) [system]"
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
    
    download_and_extract "$url" "$ninja_dir"
    chmod +x "$ninja_dir/ninja" 2>/dev/null || true
    log_ok "ninja $version"
}

setup_sdl2() {
    local sdl_dir="$TOOLS_DIR/SDL2"
    
    if [[ -f "$sdl_dir/lib/libSDL2.a" ]] || [[ -f "$sdl_dir/lib/libSDL2.dll.a" ]]; then
        log_ok "SDL2"
        return 0
    fi
    
    # Get latest SDL2 version (not SDL3)
    local version
    version=$(gh api "repos/libsdl-org/SDL/releases" --jq '[.[] | select(.tag_name | startswith("release-2"))][0].tag_name' | sed 's/release-//')
    
    if [[ -z "$version" ]]; then
        log_warn "Could not determine SDL2 version, skipping"
        return 0
    fi
    
    log_info "Installing SDL2 $version..."
    
    local url
    case "$OS" in
        linux)
            # Linux: need to install via package manager or compile
            log_warn "SDL2 on Linux: install via package manager"
            echo "  sudo apt install libsdl2-dev"
            return 0
            ;;
        macos)
            log_warn "SDL2 on macOS: install via Homebrew"
            echo "  brew install sdl2"
            return 0
            ;;
        windows)
            url="https://github.com/libsdl-org/SDL/releases/download/release-${version}/SDL2-devel-${version}-mingw.tar.gz"
            ;;
    esac
    
    download_and_extract "$url" "$sdl_dir"
    
    # SDL2 mingw archive has x86_64-w64-mingw32 subdirectory
    if [[ -d "$sdl_dir/SDL2-${version}/x86_64-w64-mingw32" ]]; then
        mv "$sdl_dir/SDL2-${version}/x86_64-w64-mingw32"/* "$sdl_dir/"
        rm -rf "$sdl_dir/SDL2-${version}"
    fi
    
    log_ok "SDL2 $version"
}

setup_emscripten() {
    local emsdk_dir="$TOOLS_DIR/emsdk"
    
    if [[ -d "$emsdk_dir/upstream/emscripten" ]]; then
        log_ok "emscripten"
        return 0
    fi
    
    log_info "Installing Emscripten SDK..."
    
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
    log_info "=== Installing shared tools ==="
    
    mkdir -p "$TOOLS_DIR"
    
    setup_cmake
    setup_ninja
    setup_sdl2
    setup_emscripten
    
    echo ""
    log_ok "Tools installed in $TOOLS_DIR"
}

# =============================================================================
# Create Symlinks (point project tools to shared tools)
# =============================================================================

create_symlinks() {
    log_info "=== Creating symlinks to shared tools ==="
    
    # midi-studio/core/sdl/tools -> ../../../tools
    local ms_tools="$WORKSPACE/midi-studio/core/sdl/tools"
    if [[ -d "$WORKSPACE/midi-studio/core/sdl" ]]; then
        if [[ -L "$ms_tools" ]]; then
            log_ok "midi-studio/core/sdl/tools (symlink exists)"
        elif [[ -d "$ms_tools" ]]; then
            log_warn "midi-studio/core/sdl/tools exists as directory, skipping symlink"
        else
            ln -s "../../../tools" "$ms_tools"
            log_ok "midi-studio/core/sdl/tools -> ../../../tools"
        fi
    fi
}

# =============================================================================
# Configure PATH
# =============================================================================

configure_path() {
    log_info "=== Configuring PATH ==="
    
    local paths_to_add=(
        "$WORKSPACE/midi-studio/commands"
        "$WORKSPACE/open-control/cli-tools/bin"
        "$TOOLS_DIR/cmake/bin"
        "$TOOLS_DIR/ninja"
    )
    
    # Detect shell config file
    local shell_config=""
    case "$(basename "${SHELL:-bash}")" in
        zsh)  shell_config="$HOME/.zshrc" ;;
        bash)
            if [[ -f "$HOME/.bash_profile" ]]; then
                shell_config="$HOME/.bash_profile"
            else
                shell_config="$HOME/.bashrc"
            fi
            ;;
        *)    shell_config="$HOME/.profile" ;;
    esac
    
    # Check if already configured
    if grep -q "petitechose-audio/setup" "$shell_config" 2>/dev/null; then
        log_ok "PATH already configured in $shell_config"
        return 0
    fi
    
    echo ""
    echo "Add the following to $shell_config:"
    echo ""
    echo "# petitechose-audio/setup"
    echo "export PATH=\"${paths_to_add[0]}:\$PATH\""
    echo "export PATH=\"${paths_to_add[1]}:\$PATH\""
    echo "export PATH=\"${paths_to_add[2]}:\$PATH\""
    echo "export PATH=\"${paths_to_add[3]}:\$PATH\""
    echo ""
    
    read -p "Add automatically? [y/N] " yn
    if [[ "$yn" == "y" || "$yn" == "Y" ]]; then
        {
            echo ""
            echo "# petitechose-audio/setup"
            for p in "${paths_to_add[@]}"; do
                echo "export PATH=\"$p:\$PATH\""
            done
        } >> "$shell_config"
        log_ok "PATH added to $shell_config"
        log_warn "Run: source $shell_config"
    fi
}

# =============================================================================
# Optional: Rust, PlatformIO
# =============================================================================

setup_optional() {
    log_info "=== Optional tools ==="
    
    # Rust
    if command -v cargo &>/dev/null; then
        log_ok "rust ($(cargo --version | cut -d' ' -f2))"
    else
        echo ""
        read -p "Install Rust? (needed for oc-bridge) [y/N] " yn
        if [[ "$yn" == "y" || "$yn" == "Y" ]]; then
            curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
            log_ok "rust installed"
        fi
    fi
    
    # PlatformIO
    if command -v pio &>/dev/null; then
        log_ok "platformio ($(pio --version 2>/dev/null | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1))"
    else
        echo ""
        read -p "Install PlatformIO? (needed for Teensy) [y/N] " yn
        if [[ "$yn" == "y" || "$yn" == "Y" ]]; then
            pip install platformio
            log_ok "platformio installed"
        fi
    fi
}

# =============================================================================
# Main
# =============================================================================

main() {
    echo "============================================"
    echo " MIDI Studio - Development Environment Setup"
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
        # create_symlinks  # Uncomment to enable symlinks
        # echo ""
    fi
    
    configure_path
    echo ""
    
    setup_optional
    
    echo ""
    echo "============================================"
    log_ok "Setup complete!"
    echo ""
    echo "Next steps:"
    echo "  1. Restart your terminal (or source your shell config)"
    echo "  2. Run: ms help"
    echo "============================================"
}

main "$@"
