# Commandes utiles

## midi-studio

```bash
# Alias définis dans shell
ms core          # cd midi-studio/core && pio run
ms bitwig        # cd midi-studio/plugin-bitwig && pio run
ms run core      # Build + run native core
ms run bitwig    # Build + run native bitwig

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
# Voir tous les repos
find ~/petitechose-audio -maxdepth 3 -name ".git" -type d

# Status de tous les repos
for d in ~/petitechose-audio/open-control/*/; do echo "=== $d ===" && git -C "$d" status -s; done
for d in ~/petitechose-audio/midi-studio/*/; do echo "=== $d ===" && git -C "$d" status -s; done
```

## Recherche

```bash
# Chercher dans le code
grep -rn "pattern" --include="*.hpp" --include="*.cpp" ~/petitechose-audio

# Fichiers modifiés récemment
find ~/petitechose-audio -name "*.hpp" -mtime -1 | grep -v .pio | grep -v .git
```

---

## Voir aussi

- `midi-studio/overview.md` - Structure des projets et chemins clés
