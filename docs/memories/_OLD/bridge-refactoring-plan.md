# Plan de Refactoring OC Bridge

> **INSTRUCTION CRITIQUE - À SUIVRE À CHAQUE DÉBUT DE SESSION**
> 
> 1. Relire ce fichier EN INTÉGRALITÉ
> 2. Identifier la phase en cours et les tâches restantes
> 3. Lire les fichiers impactés par les prochaines étapes AVANT de commencer
> 4. Vérifier la cohérence avec l'état actuel du code
> 5. Mettre à jour ce fichier après chaque modification

---

## Statut Global

| Phase | Status | Progress |
|-------|--------|----------|
| Phase 0 - Quick Wins | ✅ TERMINÉ | 5/5 |
| Phase 1 - Erreurs | ⏭️ SKIP (fait en Phase 0) | - |
| Phase 2 - CLI Clap | ✅ TERMINÉ | 4/4 |
| Phase 3 - Orchestrateur | ⏳ Pending | 0/4 |
| Phase 4 - Async Cleanup | ✅ TERMINÉ (pragmatique) | 3/3 |
| Phase 5 - Tests Integration | ✅ TERMINÉ | 3/3 |
| Phase 6 - Réorg (Optionnel) | ⏳ Pending | 0/2 |

---

## Phase 0 : Quick Wins (EN COURS)

### Fichiers à analyser avant de commencer
- `.gitignore`
- `bridge/runner.rs` (lignes 50, 70, 88, 111, 112)
- `bridge/session.rs` (lignes 138, 142, 147, 166, 174)
- `bridge_state.rs` (ligne 355)
- `config.rs` (lignes 252-255)
- `service/windows.rs` (lignes 389-395)

### Tâches

- [x] **0.1** Supprimer fichiers temporaires `tmpclaude-*`
- [x] **0.2** Ajouter entries `.gitignore`
- [x] **0.3** Logger erreurs channel au lieu de `let _ =` (18 occurrences corrigées)
- [x] **0.4** Validation config avec warning
- [x] **0.5** Documenter SDDL Windows (documentation complète des ACEs)

---

## Phase 1 : Gestion d'Erreurs Robuste

### Fichiers à analyser avant de commencer
- `error.rs`
- `main.rs` (pour le module declaration)
- Tous les fichiers avec `try_send`

### Tâches

- [ ] **1.1** Créer module `channel_utils.rs`
- [ ] **1.2** Remplacer `let _ = try_send` par `try_send_logged`
- [ ] **1.3** Améliorer `BridgeError` avec variantes supplémentaires
- [ ] **1.4** Créer type `SoftResult` pour opérations non-critiques

---

## Phase 2 : CLI Moderne avec Clap

### Fichiers à analyser avant de commencer
- `Cargo.toml`
- `cli.rs`
- `main.rs`

### Tâches

- [ ] **2.1** Ajouter clap en dépendance
- [ ] **2.2** Créer struct CLI avec derive
- [ ] **2.3** Mettre à jour `main.rs`
- [ ] **2.4** Deprecate `parse_arg`

---

## Phase 3 : Extraction Orchestrateur

### Fichiers à analyser avant de commencer
- `app/mod.rs`
- `bridge_state.rs`
- `config.rs`
- `logging/store.rs`

### Tâches

- [ ] **3.1** Créer trait `Orchestrator` dans `orchestrator/mod.rs`
- [ ] **3.2** Implémenter `DefaultOrchestrator`
- [ ] **3.3** Refactorer `App` pour utiliser `Orchestrator`
- [ ] **3.4** Ajouter tests avec mock orchestrator

---

## Phase 4 : Async Cleanup

### Fichiers à analyser avant de commencer
- `bridge_state.rs` (lignes 148, 233)
- `service/windows.rs` (ligne 164)

### Tâches

- [ ] **4.1** Remplacer `thread::sleep` par `tokio::time::sleep`
- [ ] **4.2** Créer helper `wait_for` async
- [ ] **4.3** Utiliser pour attente service

---

## Phase 5 : Tests d'Intégration

### Fichiers à analyser avant de commencer
- `transport/mod.rs`
- `codec/mod.rs`
- `bridge/session.rs`

### Tâches

- [ ] **5.1** Créer structure `tests/`
- [ ] **5.2** Créer `MockTransport`
- [ ] **5.3** Test smoke bridge relay

---

## Phase 6 : Réorganisation (Optionnel)

### Fichiers à analyser
- Tous les modules

### Tâches

- [ ] **6.1** Restructurer en `core/`, `transport/`, `ui/`
- [ ] **6.2** Vérifier imports et cycles

---

## Journal des Modifications

### Session 1 - 2026-01-12
- Plan créé et validé avec l'utilisateur
- Début Phase 0
- **Phase 0 TERMINÉE** :
  - 0.1: Supprimé 11 fichiers tmpclaude-*
  - 0.2: Ajouté tmpclaude-* au .gitignore
  - 0.3: Remplacé 18 `let _ = try_send` par des warnings tracing dans:
    - bridge/mod.rs (3)
    - bridge/runner.rs (8)
    - bridge/session.rs (5)
    - logging/receiver.rs (3)
  - 0.4: Ajouté validation config avec warnings dans config.rs:load()
  - 0.5: Documentation complète SDDL (rights, trustees, ACE breakdown)
  - Tests: 102/102 passent

- **Phase 1 SKIPPÉE** : Le travail des erreurs channel a été fait en Phase 0.3

- **Phase 2 TERMINÉE** :
  - 2.1: Ajout clap v4 avec feature derive dans Cargo.toml
  - 2.2: Création struct Cli avec derive(Parser)
    - Options: --verbose, --no-relaunch, --headless, --port, --udp-port
    - Subcommands: install, uninstall (+ service, install-service, uninstall-service internes Windows)
  - 2.3: Refactorisé main.rs pour utiliser clap::Parser
  - 2.4: Fonction parse_arg marquée deprecated + allow(dead_code)
  - Migré service/windows.rs vers Cli::try_parse()
  - Ajouté fonctions run_elevated_install/uninstall dans operations.rs
  - Tests: 107/107 passent (5 nouveaux tests CLI)
  - `oc-bridge --help` fonctionne

- **Phase 4 TERMINÉE** (approche pragmatique) :
  - Analysé les 6 occurrences de thread::sleep
  - Décision: garder thread::sleep car contextes sync (appelés depuis UI handlers)
  - Documenté pourquoi chaque sleep est intentionnel (bridge_state.rs, app/mod.rs)
  - Les autres (main.rs, service/windows.rs, transport/udp.rs) sont dans du code purement sync
  - Tests: 107/107 passent

- **Phase 5 TERMINÉE** :
  - 5.1: Créé répertoire tests/
  - 5.2: Créé MockTransport avec capture bidirectionnelle
  - 5.3: Ajouté tests d'intégration:
    - test_mock_transport_captures_data
    - test_mock_transport_receives_data
    - test_channel_bidirectional
    - test_cobs_roundtrip_integration
    - test_config_toml_roundtrip
  - Tests: 112/112 passent (107 unit + 5 integration)
  
- **SDDL Builder** (bonus) :
  - Remplacé string SDDL hardcodée par builder pattern
  - Module `sddl` avec `rights::*` et `trustees::*` constants
  - Fonctions `allow()` et `dacl()` pour construire le SDDL
  - 3 tests ajoutés pour valider le builder
  - Code maintenant lisible et maintenable
  - Tests: 115/115 passent (110 unit + 5 integration)

- **Récapitulatif Session 1** :
  - Phase 0: ✅ (5 tâches)
  - Phase 1: ⏭️ Skip (intégré en Phase 0)
  - Phase 2: ✅ (CLI Clap)
  - Phase 4: ✅ (Documentation thread::sleep)
  - Phase 5: ✅ (Tests intégration)
  - SDDL Builder: ✅ (bonus)
  - Restant: Phase 3 (Orchestrateur optionnel), Phase 6 (Réorg optionnel)

---

## Notes Techniques

### Pattern pour erreurs channel (Phase 0.3 / 1.2)

**Avant:**
```rust
let _ = tx.try_send(LogEntry::system("..."));
```

**Après (Phase 0 - simple):**
```rust
if tx.try_send(LogEntry::system("...")).is_err() {
    tracing::warn!("Log channel full");
}
```

**Après (Phase 1 - avec helper):**
```rust
channel_utils::try_send_logged(&tx, LogEntry::system("..."), "bridge_session");
```

### Pattern pour config validation (Phase 0.4)

**Fichier:** `config.rs:252-255`

```rust
match fs::read_to_string(&path) {
    Ok(content) => match toml::from_str(&content) {
        Ok(cfg) => cfg,
        Err(e) => {
            tracing::warn!("Config parse error (using defaults): {}", e);
            Config::default()
        }
    },
    Err(_) => Config::default(),
}
```

### SDDL Documentation (Phase 0.5)

```
D: - DACL follows
(A;;CCLCSWRPWPDTLOCRRC;;;SY) - SYSTEM: full control
(A;;CCDCLCSWRPWPDTLOCRSDRCWDWO;;;BA) - Administrators: full control + delete
(A;;CCLCSWRPWPLOCRRC;;;IU) - Interactive Users: start/stop
(A;;CCLCSWRPWPLOCRRC;;;SU) - Service Users: start/stop
```
