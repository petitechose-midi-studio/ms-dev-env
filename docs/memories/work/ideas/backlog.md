# Backlog - Idées à explorer

## Protocol-codegen : backends TypeScript + Python

**Date** : 2026-01-20
**Priorité** : Moyenne (quand 3+ types presets ou Web GUI)
**Effort estimé** : ~12-15h

### Contexte

`protocol-codegen` génère actuellement du C++ et Java depuis des définitions Python. Pour la conversion JSON ↔ binaire des presets, il serait judicieux d'ajouter des backends TypeScript et Python.

### Proposition

Ajouter à `open-control/protocol-codegen/` :

```
generators/
├── binary/
│   ├── cpp/           ✅ existe
│   ├── java/          ✅ existe
│   ├── typescript/    🆕 à créer
│   └── python/        🆕 à créer
```

### Génération TypeScript

```typescript
// Interfaces
export interface MacroPageData {
  name: string;
  cc: number[];
  channel: number[];
  values: number[];
}

// Encoder
export function encodeMacroPageData(data: MacroPageData): Uint8Array;

// Decoder
export function decodeMacroPageData(bytes: Uint8Array): MacroPageData;
```

### Génération Python

```python
# Pydantic ou dataclass
@dataclass
class MacroPageData:
    name: str
    cc: list[int]
    channel: list[int]
    values: list[float]

# Encoder/Decoder
def encode_macro_page_data(data: MacroPageData) -> bytes: ...
def decode_macro_page_data(data: bytes) -> MacroPageData: ...
```

### Cas d'usage

| Backend | Usage |
|---------|-------|
| TypeScript | Web GUI (Svelte), helpers WASM |
| Python | CLI tools (`ms preset convert`), tests, bridge |

### Quand implémenter

- [ ] 3+ types de preset différents
- [ ] Début développement Web GUI
- [ ] Besoin de CLI `ms preset export/import`
- [ ] Changements fréquents du format binaire

### Bénéfices

- Single source of truth (schema Python)
- Type safety cross-language
- Pas de drift entre implémentations
- Documentation implicite via schema

---

## Bridge REST API pour storage

**Date** : 2026-01-20
**Priorité** : Haute (bloque persistence WASM)
**Effort estimé** : ~3h

### Contexte

WASM ne peut pas accéder au filesystem. Bridge doit servir les fichiers via HTTP.

### Endpoints

```
GET  /files/{path}   → lire fichier
PUT  /files/{path}   → écrire fichier
GET  /files          → lister fichiers
```

### Implémentation

- Ajouter `axum` au bridge Rust
- Nouveau flag CLI `--http-port 8080`
- Storage dans `~/.config/open-control/storage/`

---

## Device storage proxy

**Date** : 2026-01-20
**Priorité** : Moyenne (après REST local)
**Effort estimé** : ~6h

### Contexte

Permettre à la Web GUI de lire/écrire le storage du Teensy via bridge.

### Endpoints

```
GET  /device/files/{path}   → lire depuis Teensy
PUT  /device/files/{path}   → écrire sur Teensy
GET  /device/status         → état connexion
```

### Prérequis

- Protocole Serial `StorageRead`/`StorageWrite` côté Teensy
- Bridge intercepte et proxy vers Serial

---

## Web GUI preset manager

**Date** : 2026-01-20
**Priorité** : Basse (après bridge REST)
**Effort estimé** : ~1-2 semaines

### Stack recommandée

- **Svelte** (léger, compile en vanilla JS)
- **Vite** (build rapide)
- **TypeScript**

### Features

- File browser (local + device)
- Drag & drop entre local et device
- Conversion JSON ↔ binaire
- Édition presets en JSON

### Emplacement

`open-control/gui/` ou repo séparé
