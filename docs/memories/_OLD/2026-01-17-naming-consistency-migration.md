# Migration: Cohérence du nommage Transport/Encoding

**Date**: 2026-01-17
**Statut**: Terminé
**Impact**: open-control (7 repos), midi-studio (2 repos), protocol-codegen

---

## Objectif

Aligner le nommage à travers toutes les codebases pour refléter correctement les concepts :

| Concept | Actuel (incohérent) | Nouveau (cohérent) |
|---------|---------------------|-------------------|
| Interface transport frames | `IMessageTransport` | `IFrameTransport` |
| Encodage 8-bit binaire | `Serial8` | `Binary` |

### Raison du changement

1. **`IMessageTransport`** suggère qu'on transporte des "messages" abstraits, mais l'interface transporte des **frames** binaires bruts
2. **`Serial8`** mélange transport ("Serial") et encodage ("8-bit"), alors que cet encodage est utilisé sur UDP, WebSocket, TCP, etc.

---

## Architecture cible

```
┌─────────────────────────────────────────────────────┐
│                    Encoding                          │
│              Binary    vs    SysEx                   │
│             (8-bit)        (7-bit)                   │
├─────────────────────────────────────────────────────┤
│                    Framing                           │
│         (géré par transport)  │  F0..F7 (inclus)    │
├─────────────────────────────────────────────────────┤
│               IFrameTransport  │  IMidiTransport    │
│   UdpTransport, WebSocket,     │  UsbMidi,          │
│   UsbSerial (COBS)             │  LibreMidi         │
└─────────────────────────────────────────────────────┘
```

---

## Phase 1: IMessageTransport → IFrameTransport

### 1.1 Fichiers à modifier (SCRIPTABLE)

Ces changements sont des rechercher/remplacer simples et sûrs.

#### framework (open-control)

```bash
# Renommer le fichier
mv src/oc/hal/IMessageTransport.hpp src/oc/hal/IFrameTransport.hpp

# Remplacements dans tous les fichiers .hpp/.cpp
sed -i 's/IMessageTransport/IFrameTransport/g' src/oc/hal/IFrameTransport.hpp
sed -i 's/IMessageTransport/IFrameTransport/g' src/oc/context/IContext.hpp
sed -i 's/IMessageTransport/IFrameTransport/g' src/oc/context/APIs.hpp
sed -i 's/IMessageTransport/IFrameTransport/g' src/oc/context/ContextManager.hpp
sed -i 's/IMessageTransport/IFrameTransport/g' src/oc/app/OpenControlApp.hpp
sed -i 's/IMessageTransport/IFrameTransport/g' src/oc/app/AppBuilder.hpp
sed -i 's/IMessageTransport/IFrameTransport/g' src/oc/app/AppBuilder.cpp
```

#### hal-teensy (open-control)

```bash
sed -i 's/IMessageTransport/IFrameTransport/g' src/oc/hal/teensy/UsbSerial.hpp
```

#### hal-net (open-control)

```bash
sed -i 's/IMessageTransport/IFrameTransport/g' src/oc/hal/net/UdpTransport.hpp
sed -i 's/IMessageTransport/IFrameTransport/g' src/oc/hal/net/WebSocketTransport.hpp
```

#### hal-sdl (open-control)

```bash
sed -i 's/IMessageTransport/IFrameTransport/g' src/oc/hal/sdl/AppBuilder.hpp
```

#### midi-studio/plugin-bitwig (MANUEL - fichier customisé)

```bash
# BitwigProtocol.hpp est customisé, vérifier manuellement
sed -i 's/IMessageTransport/IFrameTransport/g' src/protocol/BitwigProtocol.hpp
```

### 1.2 Vérification post-Phase 1

```bash
# Vérifier qu'il ne reste aucune occurrence
grep -r "IMessageTransport" --include="*.hpp" --include="*.cpp" .
```

### 1.3 Tests Phase 1

```bash
# Build Teensy
cd ~/petitechose-audio/midi-studio && ms core && ms bitwig

# Build Native  
ms run core --build-only && ms run bitwig --build-only
```

---

## Phase 2: Serial8 → Binary (protocol-codegen)

### 2.1 Renommage des répertoires (SCRIPTABLE)

```bash
cd ~/petitechose-audio/open-control/protocol-codegen/src/protocol_codegen

# Répertoires principaux
mv generators/serial8 generators/binary
mv generators/orchestrators/serial8 generators/orchestrators/binary
mv generators/protocols/serial8 generators/protocols/binary
mv methods/serial8 methods/binary

# Fichiers compositions
mv generators/compositions/serial8_cpp.py generators/compositions/binary_cpp.py
mv generators/compositions/serial8_java.py generators/compositions/binary_java.py
```

### 2.2 Renommage des symboles Python (SCRIPTABLE avec prudence)

#### Table des remplacements

| Pattern | Remplacement | Fichiers concernés |
|---------|--------------|-------------------|
| `Serial8EncodingStrategy` | `BinaryEncodingStrategy` | encoding.py, __init__.py, components.py, tests |
| `Serial8FramingMixin` | `BinaryFramingMixin` | framing.py, __init__.py, compositions |
| `Serial8Config` | `BinaryConfig` | config.py, __init__.py, generator.py |
| `Serial8Limits` | `BinaryLimits` | config.py, __init__.py |
| `Serial8Structure` | `BinaryStructure` | config.py, __init__.py |
| `Serial8Generator` | `BinaryGenerator` | generator.py, __init__.py |
| `Serial8Components` | `BinaryComponents` | components.py, __init__.py |
| `Serial8CppProtocolRenderer` | `BinaryCppProtocolRenderer` | compositions/*.py |
| `Serial8JavaProtocolRenderer` | `BinaryJavaProtocolRenderer` | compositions/*.py |
| `generate_serial8_protocol` | `generate_binary_protocol` | generator.py, __init__.py |
| `serial8_calculator` | `binary_calculator` | tests/*.py |
| `TestPayloadCalculatorSerial8` | `TestPayloadCalculatorBinary` | tests/*.py |
| `TestSerial8Strategy` | `TestBinaryStrategy` | tests/*.py |

#### Script de remplacement

```bash
cd ~/petitechose-audio/open-control/protocol-codegen

# Remplacements de classes/fonctions (ordre important: plus long d'abord)
find src tests -name "*.py" -exec sed -i \
    -e 's/Serial8EncodingStrategy/BinaryEncodingStrategy/g' \
    -e 's/Serial8FramingMixin/BinaryFramingMixin/g' \
    -e 's/Serial8CppProtocolRenderer/BinaryCppProtocolRenderer/g' \
    -e 's/Serial8JavaProtocolRenderer/BinaryJavaProtocolRenderer/g' \
    -e 's/Serial8Components/BinaryComponents/g' \
    -e 's/Serial8Generator/BinaryGenerator/g' \
    -e 's/Serial8Structure/BinaryStructure/g' \
    -e 's/Serial8Limits/BinaryLimits/g' \
    -e 's/Serial8Config/BinaryConfig/g' \
    -e 's/generate_serial8_protocol/generate_binary_protocol/g' \
    -e 's/serial8_calculator/binary_calculator/g' \
    -e 's/TestPayloadCalculatorSerial8/TestPayloadCalculatorBinary/g' \
    -e 's/TestSerial8Strategy/TestBinaryStrategy/g' \
    {} \;

# Remplacements des imports de chemins
find src tests -name "*.py" -exec sed -i \
    -e 's/from.*serial8/from protocol_codegen.generators.protocols.binary/g' \
    -e 's/\.serial8\./\.binary\./g' \
    -e 's/protocols\.serial8/protocols.binary/g' \
    -e 's/orchestrators\.serial8/orchestrators.binary/g' \
    -e 's/generators\.serial8/generators.binary/g' \
    -e 's/methods\.serial8/methods.binary/g' \
    -e 's/serial8_cpp/binary_cpp/g' \
    -e 's/serial8_java/binary_java/g' \
    {} \;
```

### 2.3 Mise à jour des chaînes/commentaires (SEMI-MANUEL)

Ces changements concernent les docstrings et commentaires. Revue manuelle recommandée.

```bash
# Liste des fichiers à revoir manuellement pour les commentaires
grep -rn "Serial8" --include="*.py" src/ | grep -v "^Binary"
```

#### Remplacements sûrs dans les commentaires

| Pattern | Remplacement |
|---------|--------------|
| `"Serial8"` (nom de protocole) | `"Binary"` |
| `Serial8 protocol` | `Binary protocol` |
| `Serial8 encoding` | `Binary encoding` |
| `8-bit binary (Serial8)` | `8-bit binary (Binary)` |

### 2.4 Mise à jour du code généré (strings dans templates)

Ces fichiers génèrent du code C++/Java et contiennent des chaînes littérales.

| Fichier | Changements |
|---------|-------------|
| `generators/binary/cpp/decoder_generator.py` | Header comment |
| `generators/binary/cpp/encoder_generator.py` | Header comment |
| `generators/binary/cpp/protocol_generator.py` | Documentation template |
| `generators/protocols/binary/framing.py` | `protocol_name` property |
| `generators/protocols/binary/encoding.py` | `name` property |

```python
# Dans framing.py
@property
def protocol_name(self) -> str:
    return "Binary"  # était "Serial8"

# Dans encoding.py
@property
def name(self) -> str:
    return "Binary"  # était "Serial8"
```

### 2.5 Vérification post-Phase 2

```bash
# Aucune occurrence de Serial8 ne doit rester (sauf historique git)
grep -rn "Serial8" --include="*.py" src/ tests/

# Tests unitaires
cd ~/petitechose-audio/open-control/protocol-codegen
pytest tests/ -v
```

---

## Phase 3: Régénération du code protocol (midi-studio)

### 3.1 Régénérer les fichiers protocol

```bash
cd ~/petitechose-audio/midi-studio/plugin-bitwig

# Régénérer avec le nouveau codegen
# (commande dépend de la config du projet)
python -m protocol_codegen generate \
    --protocol binary \
    --input protocol.yaml \
    --output src/protocol/
```

### 3.2 Fichiers régénérés (NE PAS MODIFIER MANUELLEMENT)

```
src/protocol/
├── Decoder.hpp          # Régénéré
├── DecoderRegistry.hpp  # Régénéré
├── Encoder.hpp          # Régénéré
├── MessageID.hpp        # Régénéré
├── MessageStructure.hpp # Régénéré
├── ProtocolCallbacks.hpp # Régénéré
├── ProtocolConstants.hpp # Régénéré
├── Protocol.hpp.template # Régénéré (template)
└── struct/*.hpp         # Régénérés
```

### 3.3 Fichier customisé (VÉRIFIER)

`BitwigProtocol.hpp` est basé sur le template mais customisé. Vérifier que les imports sont corrects après Phase 1.

---

## Phase 4: Commits et Push

### 4.1 Ordre des commits

L'ordre est important car les repos ont des dépendances.

```
1. framework          # Interface de base
2. hal-teensy         # Dépend de framework
3. hal-net            # Dépend de framework
4. hal-sdl            # Dépend de framework
5. protocol-codegen   # Indépendant mais génère pour midi-studio
6. midi-studio/core   # Dépend de framework
7. midi-studio/plugin-bitwig # Dépend de framework + protocol-codegen
```

### 4.2 Messages de commit

```bash
# Phase 1
git commit -m "refactor: rename IMessageTransport to IFrameTransport

More accurate naming: this interface transports binary frames,
not abstract messages. The framing (COBS, length-prefix) is
handled by the transport implementation."

# Phase 2
git commit -m "refactor: rename Serial8 to Binary encoding

Serial8 incorrectly suggested a Serial transport, but this
encoding is transport-agnostic (used on UDP, WebSocket, etc.).
Binary better describes what it is: 8-bit native encoding."
```

---

## Analyse des risques

### Risques faibles (SCRIPTABLE)

| Changement | Risque | Raison |
|------------|--------|--------|
| Renommer fichier IMessageTransport.hpp | Faible | Nom unique, pas d'ambiguïté |
| sed IMessageTransport → IFrameTransport | Faible | Pattern unique, pas de faux positifs |
| Renommer répertoires serial8/ → binary/ | Faible | Chemin explicite |
| Renommer classes Serial8* → Binary* | Faible | Patterns uniques avec majuscules |

### Risques moyens (VÉRIFICATION REQUISE)

| Changement | Risque | Raison |
|------------|--------|--------|
| Imports Python après renommage | Moyen | Chemins relatifs peuvent casser |
| Chaînes dans templates de code | Moyen | Peut affecter code généré |
| Tests après renommage | Moyen | Fixtures et mocks peuvent référencer anciens noms |

### Risques élevés (MANUEL)

| Changement | Risque | Raison |
|------------|--------|--------|
| BitwigProtocol.hpp | Élevé | Fichier customisé, logique métier |
| Commentaires/docstrings | Moyen | Contexte important, pas juste rechercher/remplacer |

---

## Checklist d'exécution

### Pré-requis
- [ ] Tous les repos sont clean (pas de changements non commités)
- [ ] Tests passent avant migration
- [ ] Backup ou branches créées

### Phase 1: IFrameTransport
- [ ] 1.1 Renommer fichier dans framework
- [ ] 1.2 sed dans framework (6 fichiers)
- [ ] 1.3 sed dans hal-teensy (1 fichier)
- [ ] 1.4 sed dans hal-net (2 fichiers)
- [ ] 1.5 sed dans hal-sdl (1 fichier)
- [ ] 1.6 Vérifier BitwigProtocol.hpp manuellement
- [ ] 1.7 grep vérification (0 occurrences IMessageTransport)
- [ ] 1.8 Build Teensy (ms core, ms bitwig)
- [ ] 1.9 Build Native (ms run core, ms run bitwig)
- [ ] 1.10 Commit framework
- [ ] 1.11 Commit hal-teensy
- [ ] 1.12 Commit hal-net
- [ ] 1.13 Commit hal-sdl
- [ ] 1.14 Commit midi-studio (si changé)

### Phase 2: Binary encoding
- [ ] 2.1 Renommer répertoires (4 mv)
- [ ] 2.2 Renommer fichiers compositions (2 mv)
- [ ] 2.3 sed classes/fonctions
- [ ] 2.4 sed imports/chemins
- [ ] 2.5 Vérifier manuellement framing.py et encoding.py
- [ ] 2.6 pytest tests/
- [ ] 2.7 grep vérification (0 occurrences Serial8)
- [ ] 2.8 Commit protocol-codegen

### Phase 3: Régénération
- [ ] 3.1 Régénérer protocol midi-studio/plugin-bitwig
- [ ] 3.2 Vérifier BitwigProtocol.hpp compatible
- [ ] 3.3 Build et test
- [ ] 3.4 Commit midi-studio

### Phase 4: Push
- [ ] 4.1 Push framework
- [ ] 4.2 Push hal-teensy
- [ ] 4.3 Push hal-net
- [ ] 4.4 Push hal-sdl
- [ ] 4.5 Push protocol-codegen
- [ ] 4.6 Push midi-studio/core
- [ ] 4.7 Push midi-studio/plugin-bitwig

---

## Script d'exécution automatisé (Phase 1 uniquement)

```bash
#!/bin/bash
# migration-phase1-iframe-transport.sh
# Usage: ./migration-phase1-iframe-transport.sh [--dry-run]

set -e

DRY_RUN=false
[[ "$1" == "--dry-run" ]] && DRY_RUN=true

OC_ROOT=~/petitechose-audio/open-control
MS_ROOT=~/petitechose-audio/midi-studio

run() {
    if $DRY_RUN; then
        echo "[DRY-RUN] $*"
    else
        echo "[EXEC] $*"
        eval "$@"
    fi
}

echo "=== Phase 1: IMessageTransport → IFrameTransport ==="

# Framework
echo "--- framework ---"
cd "$OC_ROOT/framework"
run "git mv src/oc/hal/IMessageTransport.hpp src/oc/hal/IFrameTransport.hpp"
for f in src/oc/hal/IFrameTransport.hpp \
         src/oc/context/IContext.hpp \
         src/oc/context/APIs.hpp \
         src/oc/context/ContextManager.hpp \
         src/oc/app/OpenControlApp.hpp \
         src/oc/app/AppBuilder.hpp \
         src/oc/app/AppBuilder.cpp; do
    [[ -f "$f" ]] && run "sed -i 's/IMessageTransport/IFrameTransport/g' $f"
done

# hal-teensy
echo "--- hal-teensy ---"
cd "$OC_ROOT/hal-teensy"
run "sed -i 's/IMessageTransport/IFrameTransport/g' src/oc/hal/teensy/UsbSerial.hpp"

# hal-net
echo "--- hal-net ---"
cd "$OC_ROOT/hal-net"
run "sed -i 's/IMessageTransport/IFrameTransport/g' src/oc/hal/net/UdpTransport.hpp"
run "sed -i 's/IMessageTransport/IFrameTransport/g' src/oc/hal/net/WebSocketTransport.hpp"

# hal-sdl
echo "--- hal-sdl ---"
cd "$OC_ROOT/hal-sdl"
run "sed -i 's/IMessageTransport/IFrameTransport/g' src/oc/hal/sdl/AppBuilder.hpp"

# midi-studio
echo "--- midi-studio/plugin-bitwig ---"
cd "$MS_ROOT/plugin-bitwig"
run "sed -i 's/IMessageTransport/IFrameTransport/g' src/protocol/BitwigProtocol.hpp"

echo ""
echo "=== Vérification ==="
echo "Recherche des occurrences restantes de IMessageTransport..."
grep -rn "IMessageTransport" --include="*.hpp" --include="*.cpp" "$OC_ROOT" "$MS_ROOT" || echo "OK: Aucune occurrence trouvée"

echo ""
echo "=== Phase 1 terminée ==="
echo "Prochaines étapes:"
echo "  1. Vérifier manuellement BitwigProtocol.hpp"
echo "  2. Build: ms core && ms bitwig"
echo "  3. Build: ms run core --build-only && ms run bitwig --build-only"
echo "  4. Commiter chaque repo"
```

---

## Historique

| Date | Action | Statut |
|------|--------|--------|
| 2026-01-17 | Création du plan | Terminé |
| 2026-01-17 | Phase 1: IMessageTransport -> IFrameTransport | Terminé |
| 2026-01-17 | Phase 2: Serial8 -> Binary (protocol-codegen) | Terminé |
| 2026-01-17 | Phase 3: Régénération protocol midi-studio | Terminé |
| 2026-01-17 | Phase 4: Push all repos | Terminé |

## Résumé des commits

### protocol-codegen
- `b9c9361` - refactor: rename Serial8 to Binary encoding

### midi-studio/plugin-bitwig  
- `580eab0` - refactor: rename Serial8 to Binary protocol config
