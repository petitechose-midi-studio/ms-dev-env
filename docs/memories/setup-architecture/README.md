# Architecture Setup & Distribution

> Plan pour une installation simple, portable et reproductible.

## Objectifs

1. **Simplicite** : `git clone` + `ms setup` = pret a l'emploi
2. **Portabilite** : Fonctionne sur Windows, Linux, macOS sans dependances systeme
3. **Reproductibilite** : Meme environnement partout (toolchains bundlees)
4. **Zero admin** : Pas de sudo/admin pour l'usage quotidien

---

## Modes d'installation

### Mode User (defaut)

```bash
git clone https://github.com/miu-lab/midi-studio
cd midi-studio
./ms setup              # ~30 sec, telecharge binaires
ms run core             # Fonctionne immediatement
```

- Telecharge uniquement les **binaires pre-compiles**
- Pas de toolchains (pas de Zig, Rust, Java, Emscripten...)
- Setup ultra-rapide (~50MB au lieu de ~2GB)

### Mode Dev

```bash
git clone https://github.com/miu-lab/midi-studio
cd midi-studio
./ms setup --dev        # ~5 min, telecharge toolchains
ms build core           # Build from source
```

- Telecharge **toutes les toolchains**
- Peut modifier et rebuilder tous les composants

---

## Structure du workspace

```
pc/
├── bin/                          # Binaires (GitHub Releases, PAS dans git)
│   ├── .version                  # Tag de la release actuelle
│   ├── core/
│   │   ├── native/
│   │   │   ├── windows/midi_studio_core.exe
│   │   │   ├── linux/midi_studio_core
│   │   │   └── macos/midi_studio_core
│   │   └── wasm/
│   │       ├── midi_studio_core.html
│   │       ├── midi_studio_core.js
│   │       └── midi_studio_core.wasm
│   ├── bitwig/
│   │   ├── native/{platform}/...
│   │   └── wasm/...
│   ├── bridge/
│   │   ├── windows/oc-bridge.exe
│   │   ├── linux/oc-bridge
│   │   └── macos/oc-bridge
│   └── extension/
│       └── MidiStudio.bwextension
│
├── tools/                        # Toolchains (mode --dev uniquement)
│   ├── bin/                      # Wrappers (zig-cc, zig-cxx)
│   ├── cmake/
│   ├── ninja/
│   ├── zig/
│   ├── emsdk/
│   ├── jdk/
│   ├── maven/
│   ├── bun/
│   ├── platformio/               # tools/platformio/venv
│   ├── windows/SDL2/             # Windows uniquement
│   ├── linux/SDL2/               # A implementer
│   └── macos/SDL2/               # A implementer
│
├── .venv/                        # Python venv
├── open-control/                 # Submodule
├── midi-studio/                  # Submodule
└── config.toml
```

---

## Outils : Bundle vs Systeme

### Outils bundles (dans tools/)

| Outil | Chemin | Toutes plateformes |
|-------|--------|-------------------|
| cmake | `tools/cmake/` | Oui |
| ninja | `tools/ninja/` | Oui |
| zig | `tools/zig/` | Oui |
| bun | `tools/bun/` | Oui |
| java (JDK) | `tools/jdk/` | Oui |
| maven | `tools/maven/` | Oui |
| emscripten | `tools/emsdk/` | Oui |
| SDL2 | `tools/{platform}/SDL2/` | A completer (Linux/macOS) |
| platformio | `tools/platformio/venv/` | Oui |

### Outils systeme (non bundles)

| Outil | Raison | Installation |
|-------|--------|--------------|
| git | Requis pour clone | Pre-installe ou `winget`/`apt`/`brew` |
| gh | Optionnel (GitHub CLI) | `winget`/`apt`/`brew` |
| uv | Bootstrap Python deps | https://docs.astral.sh/uv/ |
| cargo/rust | Bridge build (dev only) | rustup.rs |

### Pourquoi ne pas bundler Rust ?

- Cout/benefice defavorable (~500MB pour un seul binaire)
- Rustup est deja un installeur cross-platform simple
- Le bridge ne change pas souvent
- Cargo.lock garantit la reproductibilite des deps

---

## Commandes CLI

| Commande | Mode | Description |
|----------|------|-------------|
| `ms setup` | User | Telecharge binaires depuis GitHub Release |
| `ms setup --dev` | Dev | + Telecharge toolchains |
| `ms update` | Both | Sync repos + nouveaux binaires si disponibles |
| `ms update --check` | Both | Verifie sans modifier |
| `ms build <target>` | Dev | Build from source |
| `ms run <target>` | Both | Lance l'application |
| `ms doctor` | Both | Verifie l'installation |

---

## Distribution des binaires

### Recommandation : GitHub Releases

| Critere | Git LFS | GitHub Releases |
|---------|---------|-----------------|
| Repo size | Bloated | Clean |
| Quota | 1GB free | Illimite |
| Clone speed | Lent | Rapide |
| Standard | Non | Oui |

### Workflow

1. Tag une release (`git tag v1.0.0`)
2. CI/CD build sur Windows/Linux/macOS
3. Upload binaires sur GitHub Release
4. `ms setup` telecharge depuis la release

---

## Droits administrateur

### Principe : Admin uniquement pour install service (1 fois)

| Plateforme | Action | Admin | Mecanisme |
|------------|--------|-------|-----------|
| Windows | `ms setup` | Non | - |
| Windows | `ms setup --dev` | Non | - |
| Windows | `oc-bridge install` | **UAC 1x** | Windows Service (SCM) |
| Windows | `oc-bridge start/stop` | Non | ACL configuree |
| Linux | `ms setup` | Non | - |
| Linux | `oc-bridge install` | **pkexec 1x** | dialout + udev rules |
| Linux | Usage quotidien | Non | systemd user service |
| macOS | `ms setup` | Non | - |
| macOS | `oc-bridge install` | **Non** | launchd user agent |
| macOS | Usage quotidien | Non | - |

### Detail par plateforme

#### Windows
- **Service** : Windows Service via SCM
- **Install** : UAC popup (1 fois)
- **Apres install** : ACL permet start/stop sans admin
- **Code** : `src/service/windows.rs`

#### Linux
- **Service** : systemd user service (`~/.config/systemd/user/`)
- **Install** : pkexec pour `usermod -aG dialout` + udev rules
- **Apres install** : Aucun admin requis
- **Code** : `src/service/linux.rs`

#### macOS
- **Service** : launchd user agent (`~/Library/LaunchAgents/`)
- **Install** : Aucun admin requis (user agent)
- **Code** : `src/service/macos.rs` (A IMPLEMENTER)

---

## Services par plateforme

### Windows Service

```
Type: Windows Service (SCM)
Nom: OpenControlBridge
Config: Registry
Admin: UAC pour install/uninstall
Start/Stop: Sans admin (ACL)
```

### Linux systemd

```
Type: systemd user service
Fichier: ~/.config/systemd/user/oc-bridge.service
Admin: pkexec pour dialout + udev (1 fois)
Start/Stop: systemctl --user start/stop oc-bridge
```

### macOS launchd (A implementer)

```
Type: launchd user agent
Fichier: ~/Library/LaunchAgents/com.opencontrol.bridge.plist
Admin: Jamais
Start/Stop: launchctl start/stop com.opencontrol.bridge
```

Exemple de plist :
```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" 
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.opencontrol.bridge</string>
    <key>ProgramArguments</key>
    <array>
        <string>/path/to/oc-bridge</string>
        <string>--daemon</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
</dict>
</plist>
```

---

## Plan d'implementation

### Phase 1 : Fondations (actuel)
- [x] Zig compiler pour builds natifs (wrappers zig-cc/zig-cxx)
- [x] Fix WASM MIDI (patch libremidi)
- [x] Fix Windows MIDI ports (patterns specifiques)
- [x] Fix `ms doctor` (check_tool avec ToolResolver)

### Phase 2 : Portabilite
- [ ] Bundler SDL2 pour Linux
- [ ] Bundler SDL2 pour macOS
- [ ] Deplacer PlatformIO dans `tools/`
- [ ] Implementer service macOS (launchd)

### Phase 3 : Distribution
- [ ] Implementer dual mode `ms setup` / `ms setup --dev`
- [ ] CI/CD GitHub Actions (build cross-platform)
- [ ] Publier binaires sur GitHub Releases
- [ ] Implementer `ms update`

### Phase 4 : Polish
- [ ] Documentation utilisateur
- [ ] Tests d'installation sur VM fresh
- [ ] Optimiser taille des binaires

---

## CI/CD (a creer)

```yaml
# .github/workflows/release.yml
name: Release

on:
  push:
    tags: ['v*']

jobs:
  build:
    strategy:
      matrix:
        include:
          - os: ubuntu-latest
            platform: linux
          - os: windows-latest
            platform: windows
          - os: macos-latest
            platform: macos
    
    runs-on: ${{ matrix.os }}
    
    steps:
      - uses: actions/checkout@v4
        with:
          submodules: recursive
      
      - name: Setup
        run: ./ms setup --dev
      
      - name: Build all
        run: |
          ms build core native
          ms build core wasm
          ms build bitwig native
          ms build bitwig wasm
          ms build bridge
          ms build extension
      
      - uses: actions/upload-artifact@v4
        with:
          name: binaries-${{ matrix.platform }}
          path: bin/

  release:
    needs: build
    runs-on: ubuntu-latest
    steps:
      - uses: actions/download-artifact@v4
      
      - uses: softprops/action-gh-release@v1
        with:
          files: |
            binaries-windows/**/*
            binaries-linux/**/*
            binaries-macos/**/*
```

---

## References

- [Emscripten Asyncify](https://emscripten.org/docs/porting/asyncify.html)
- [Windows Services](https://docs.microsoft.com/en-us/windows/win32/services/)
- [systemd user services](https://wiki.archlinux.org/title/Systemd/User)
- [launchd plist](https://developer.apple.com/library/archive/documentation/MacOSX/Conceptual/BPSystemStartup/Chapters/CreatingLaunchdJobs.html)
- [GitHub Releases](https://docs.github.com/en/repositories/releasing-projects-on-github)
