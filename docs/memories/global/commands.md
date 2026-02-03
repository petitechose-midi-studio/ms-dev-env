# Commandes utiles

## midi-studio

```bash
# ms (CLI)
uv run ms list

# Native simulators
uv run ms run core
uv run ms run bitwig

# Web (WASM) simulators
uv run ms web core
uv run ms web bitwig

# Note: `ms run` / `ms web` auto-start a headless `oc-bridge` (dev) using `config.toml` ports.
# For WASM, use the printed URL (it includes `bridgeWsPort=...`).

# Teensy firmware
uv run ms build core --target teensy --dry-run
uv run ms upload core --env dev
uv run ms monitor core --env dev

# Bitwig extension
uv run ms build bitwig --target extension

# Protocol generation
cd midi-studio/plugin-bitwig
./script/protocol/generate_protocol.sh

# Java extension
./script/extension/bitwig-compile.sh
./script/extension/bitwig-package.sh
```

## open-control

```bash
# Bridge
cd open-control/bridge
cargo build --release
cargo test

# Protocol codegen
cd open-control/protocol-codegen
uv sync
uv run pytest
uv run protocol-codegen --help
```

## Git

```bash
# Sync all repos (maintainer profile: includes ms-manager + distribution + examples)
uv run ms sync --repos --profile maintainer

# Voir tous les repos
WS=~/ms-dev-env
find "$WS" -maxdepth 3 -name ".git" -type d

# Status de tous les repos
for d in "$WS"/open-control/*/; do echo "=== $d ===" && git -C "$d" status -s; done
for d in "$WS"/midi-studio/*/; do echo "=== $d ===" && git -C "$d" status -s; done
```

## Recherche

```bash
# Chercher dans le code
WS=~/ms-dev-env
grep -rn "pattern" --include="*.hpp" --include="*.cpp" "$WS"

# Fichiers modifiés récemment
find "$WS" -name "*.hpp" -mtime -1 | grep -v .pio | grep -v .git
```

---

## Voir aussi

- `docs/memories/midi-studio/overview.md` - Structure des projets et chemins clés
