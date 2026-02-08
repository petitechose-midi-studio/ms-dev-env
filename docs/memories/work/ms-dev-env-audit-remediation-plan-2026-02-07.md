# Plan affine et optimal de remediation - audit ms-dev-env

Status: ACTIVE PLAN (REVISED)

Date: 2026-02-07

Owner: ms maintainers

Scope: package `ms` dans `ms-dev-env` (CLI, services, tools, release flow)

---

## 1) Objectif du plan

Ce plan remplace la version precedente par une feuille de route:

- priorisee par risque reel (security/reliability d'abord),
- executable en PRs courtes,
- mesurable par metriques objectives,
- verifiable a chaque etape avec commandes de test explicites.

Strategie globale: **secure -> stabilize -> simplify -> accelerate**.

---

## 2) Baseline objective (mesuree)

Baseline mesuree localement le 2026-02-07:

- Type check: `uv run pyright` -> `0 errors`
- Tests: `uv run pytest ms/test -q` -> `993 passed, 6 deselected`
- Lint critique: `uv run ruff check ms --select F` -> `All checks passed`
- Lint complet (etat dette): `uv run ruff check ms --statistics` -> `206 issues`
- Source: `128` fichiers, `22_367` lignes
- Tests: `78` fichiers, `13_262` lignes
- Ratio tests/source: `0.59`
- Perf locale chaude:
  - `uv run ms check --no-strict` -> `1.168s`
  - `uv run ms status --no-copy` -> `0.296s`
- Robustesse subprocess:
  - `run_process(..., timeout=...)`: `17/47` usages couverts
  - `run_silent(..., timeout=...)`: `0/18` usages couverts
- Maintenabilite:
  - Fonctions > 100 lignes: `15`
  - Fonctions > 200 lignes: `2`
  - Complexite approx >= 20: `10`
  - `except Exception`: `17`
- Architecture:
  - Cycles imports non triviaux: `1` (`ms.services.build <-> ms.output.errors`)

---

## 3) Ajustements majeurs vs plan precedent

1. Le gate `ruff` complet immediat est non optimal (206 violations):
   - Decision: gate CI critique `F` immediat, montee progressive ensuite.
2. P2 performance est de-priorisee tant que P1 n'a pas reduit la complexite release.
3. La securite bridge doit inclure un process de maintenance checksums (pas seulement verif runtime).
4. Les timeouts doivent etre centralises par classes (short/medium/long/watch) et non ajoutes ad hoc.

---

## 4) Cibles finales (Definition of Done globale)

### 4.1 Security / supply-chain

- SEC-01: 100% des binaires telecharges en mode strict verifies par checksum
- SEC-02: aucun telechargement binaire critique sans version resolue explicitement

### 4.2 Reliability / process

- REL-01: 100% des commandes reseau/GH non interactives critiques avec timeout explicite
- REL-02: politique retry documentee et testee pour lectures GH transientes
- REL-03: 0 ecriture non atomique sur state/session/plan/notes/spec/locks critiques

### 4.3 Architecture / maintenabilite

- ARC-01: 0 cycle import non documente
- MNT-01: fonctions > 200 lignes: `2 -> 0`
- MNT-02: fonctions > 100 lignes: `15 -> <= 7`
- MNT-03: complexite approx >= 20: `10 -> <= 5`
- MNT-04: `except Exception`: `17 -> <= 5`
- MNT-05: usages directs `subprocess.run/check_output`: `14 -> <= 5` (ou justifies)

### 4.4 Performance / operabilite

- PERF-01: `ms check --no-strict` chaud < `2.0s` (garde-fou), cible stretch `<= 1.5s`
- PERF-02: `ms status --no-copy` chaud < `0.35s` pour workspace local standard
- OPS-01: mode `--debug` release expose correlation_id + timings des commandes externes

### 4.5 Qualite CI

- QLT-01: `pyright` vert
- QLT-02: tests unitaires verts
- QLT-03: `ruff --select F` vert (immediat)
- QLT-04: dette lint totale < `206` puis trajectoire descendante a chaque sprint

---

## 5) Plan d'execution optimise par phases

## Phase A (S1-S2) - Security et reliability immediates

### A1 - Bridge checksum enforcement + cycle de maintenance

Valeur: eliminer le risque supply-chain le plus critique.

Actions:

1. Verif checksum stricte obligatoire pour bridge prebuilt
2. Manifest versionne des checksums bridge
3. Erreurs actionnables (asset/tag/checksum attendu)
4. Process de mise a jour checksums documente (release hygiene)

Etat actuel:

- Deja livre partiellement dans:
  - `ms/services/bridge.py`
  - `ms/data/bridge_checksums.toml`
  - `ms/test/services/test_bridge.py`

Tests obligatoires:

- `uv run pytest ms/test/services/test_bridge.py -q`
- `uv run pyright`

Metriques d'acceptation:

- 100% mismatch checksum -> installation refusee
- 100% checksum manquante en strict -> installation refusee

### A2 - Politique unifiee timeout/retry sur commandes externes critiques

Valeur: supprimer hangs et flakiness reseau/GH.

Actions:

1. Definir classes timeout (`short`, `medium`, `long`, `watch`)
2. Appliquer timeout sur tous les appels GH/reseau critiques release
3. Ajouter retry borne (max 3) sur lectures GH idempotentes
4. Uniformiser messages d'erreurs (cmd + returncode + stderr)

Etat actuel:

- Deja livre partiellement dans:
  - `ms/platform/process.py`
  - `ms/services/release/workflow.py`
  - `ms/services/release/gh.py`
  - `ms/services/release/ci.py`
  - `ms/services/release/app_repo.py`
  - `ms/services/release/dist_repo.py`
- `ms/services/release/timeouts.py` centralise les classes timeout
- retry borne (max 3) sur lectures GH idempotentes via `run_gh_read`
- Couverture timeout release (calls directs `run_process`): `23/23` (complet)
- Couverture timeout globale (calls directs `run_process`): `26/26` (complet)
- Couverture timeout globale (calls directs `run_silent`): `23/23` (complet)

Tests obligatoires:

- `uv run pytest ms/test/services/test_release_workflow.py -q`
- `uv run pytest ms/test/platform/test_process.py -q`
- `uv run pyright`

Metriques d'acceptation:

- couverture timeout release (calls directs wrappers subprocess): `23/23`
- couverture timeout globale (calls directs wrappers subprocess): `49/49`

### A3 - Rollout ecritures atomiques critiques

Valeur: eviter corruption etat sur crash/interruption.

Actions:

1. Utiliser helper unique `atomic_write_text`
2. Migrer ecritures critiques restantes (notes/spec/repos lock/setup state)
3. Ajouter tests de non regression + tests de cleanup temp file

Etat actuel:

- Deja livre partiellement dans:
  - `ms/platform/files.py`
  - `ms/tools/state.py`
  - `ms/services/release/wizard_session.py`
  - `ms/services/release/plan_file.py`
  - `ms/services/release/notes.py`
  - `ms/services/release/spec.py`
  - `ms/services/release/app_version.py`
  - `ms/services/repos.py` (`repos.lock.json`)
  - `ms/services/setup.py` (`.ms/state.toml`)
  - `ms/test/platform/test_files.py`

Tests obligatoires:

- `uv run pytest ms/test/platform/test_files.py ms/test/tools/test_state.py -q`
- `uv run pytest ms/test/services/test_release_plan_file.py ms/test/services/test_release_wizard_session.py -q`

Metriques d'acceptation:

- 0 `write_text` direct sur fichiers critiques identifies

### A4 - CI quality gates pragmatiques

Valeur: securiser la qualite sans bloquer inutilement la velocity.

Actions:

1. Gate CI `ruff --select F` (critique) + pyright + tests
2. Garder lint complet en reporting pour pilotage dette

Etat actuel:

- Deja livre dans:
  - `.github/workflows/ci.yml`
  - `pyproject.toml`

Tests obligatoires:

- `uv run ruff check ms --select F`
- `uv run pyright`
- `uv run pytest ms/test -q`

Metriques d'acceptation:

- CI verte sur gates critiques
- compteur dette lint complete publie chaque sprint

---

## Phase B (S3-S6) - Architecture et maintenabilite long terme

### B1 - Shared GH PR orchestration (app/dist)

Valeur: reduire duplication et divergence de comportement.

Actions:

1. Extraire module shared pour create/merge/wait/fallback PR
2. Parametrer policies repo (delete_branch, repo_slug, timeout)
3. Rebrancher `app_repo.py` et `dist_repo.py`

Tests obligatoires:

- tests unitaires shared + tests existants release
- `uv run pytest ms/test/services/test_release_workflow.py -q`

Metriques d'acceptation:

- duplication app/dist sur fonctions PR (open/merge/checkout/clean): baisse >= 40%
- aucune regression tests release

### B2 - Suppression cycle import `build <-> output.errors`

Valeur: clarifier boundaries, faciliter evolution.

Actions:

1. Introduire module contrat neutre (types/build errors)
2. Inverser dependances

Tests obligatoires:

- `uv run pyright`
- `uv run pytest ms/test -q`

Metriques d'acceptation:

- cycles imports non triviaux: `1 -> 0`

### B3 - Decomposition hotspots release

Valeur: reduire risque de regression et cout de maintenance.

Hotspots prioritaires:

- `ms/services/release/auto.py` (`resolve_pinned_auto_smart`)
- `ms/services/release/app_repo.py` / `dist_repo.py` (`merge_pr`)
- `ms/services/release/service.py` (prepare/publish)

Tests obligatoires:

- tests unitaires par sous-module extrait
- `uv run pytest ms/test/services -q`

Metriques d'acceptation:

- fonctions > 200 lignes: `2 -> 0`
- fonctions > 100 lignes: `15 -> <= 7`
- complexite approx >= 20: `10 -> <= 5`

### B4 - Hardening exceptions et subprocess directs

Valeur: erreurs plus explicites, observabilite meilleure.

Actions:

1. Remplacer `except Exception` par exceptions ciblees
2. Basculer usages `subprocess.*` vers wrappers communs (ou justifier)

Tests obligatoires:

- `uv run pyright`
- `uv run pytest ms/test -q`

Metriques d'acceptation:

- `except Exception`: `17 -> <= 5`
- `subprocess.run/check_output` directs: `14 -> <= 5`

---

## Phase C (S7-S10) - Performance et operabilite

### C1 - Split check rapide/profond

Valeur: temps de feedback plus court sans perdre la profondeur quand necessaire.

Actions:

1. Introduire mode rapide (no heavy ops) et mode profond
2. Documenter clear contracts des 2 modes

Tests obligatoires:

- benchmarks locaux (cold/warm) repetes
- `uv run pytest ms/test/services/test_check_service.py -q`

Metriques d'acceptation:

- `ms check --no-strict` chaud < `2.0s` (cible <= `1.5s`)

### C2 - Parallelisation selective deterministic

Valeur: gains runtime sur IO-bound sans nondeterminisme en CI.

Actions:

1. Paralleliser status/probes IO-bound
2. Conserver ordre de sortie deterministic

Tests obligatoires:

- tests unitaires ordre de sortie
- smoke local sur workspaces avec plusieurs repos

Metriques d'acceptation:

- gain >= 20% sur scenario cible (>= 8 repos)
- 0 regression snapshot UX

### C3 - Observabilite release

Valeur: triage incident rapide et reproductible.

Actions:

1. correlation_id par execution release
2. `--debug` avec timings commande par commande
3. erreurs structurees (`kind`, `hint`, `action`)

Tests obligatoires:

- tests unitaires formatting erreurs
- tests integration release dry-run

Metriques d'acceptation:

- 100% commandes externes release loggees avec duree en mode debug

---

## 6) Backlog PR recommande (ordre optimal)

PR-01: Completer A2 timeout coverage release (reste 20 appels)

PR-02: A3 atomic write wave 2 (notes/spec/repos lock/setup)

PR-03: A1 checksum lifecycle tooling + CI freshness check

PR-04: B1 shared PR orchestration module

PR-05: B2 import cycle removal `build/errors`

PR-06: B3 hotspot split `auto.py` wave 1

PR-07: B3 hotspot split `service.py` + merge flows wave 2

PR-08: B4 exception hardening

PR-09: B4 subprocess wrapper harmonization

PR-10: C1 check quick/deep mode

PR-11: C2 parallelization selective

PR-12: C3 observability/debug timings

---

## 7) Validation standard par PR

Commandes minimales:

```bash
uv run pyright
uv run pytest ms/test -q
uv run ruff check ms --select F
uv run ms check --no-strict
uv run ms status --no-copy
```

Commandes de pilotage dette (advisory):

```bash
uv run ruff check ms --statistics
```

---

## 8) Risques et mitigation

R1 - Refactor trop large en release

- mitigation: PRs courtes, wave decoupees, invariants testes

R2 - Blocage CI par dette lint historique

- mitigation: gate critique immediat (`F`), burn-down progressif lint complet

R3 - Drift checksums bridge

- mitigation: process update checksums + check CI de coherence

R4 - Nondeterminisme parallelisation

- mitigation: ordre de sortie stabilise + fallback sequence en CI

---

## 9) Etat d'avancement instantane

Livres pendant cette iteration:

- checksum strict bridge + manifest + tests
- `run_silent` avec stderr + timeout
- helper atomique + rollout state/session/plan + tests
- `ms status` TTY-aware
- gate CI `ruff --select F` + dependance dev `ruff`
- timeouts release factorises (module `timeouts.py`) + couverture release complete
- retry GH borne (max 3) sur lectures idempotentes (`gh_api_json`, `viewer_permission`, CI/oc-sdk GH read)
- atomic writes wave 2 sur notes/spec/app_version + repos lock + setup state
- tests ajoutes: `ms/test/services/test_release_gh.py`, enrichissement `test_release_spec_notes.py`
- timeouts explicites completes sur tous les callsites directs `run_process`/`run_silent` (y compris CLI/toolchains/build/bridge/git)
- burn-down Ruff complete sur scope `ms` (autofix + fixes manuels E501/B904/E741/SIM/B027/SIM115)
- policy lint explicite: `B008` ignore sur `ms/cli/**/*.py` (pattern Typer `Option/Argument` en signature)
- hardening exceptions: suppression complete des `except Exception` dans `ms` (`17 -> 0`)
- remplacement par exceptions ciblees (I/O/TOML/JSON/subprocess/base64) sur checkers, release GH, repos, config, dist, self/toolchains
- extraction orchestration PR partagee app/dist vers `ms/services/release/pr_orchestration.py`
- `app_repo.py` et `dist_repo.py` rebranches sur helpers communs (`create_pull_request`, `merge_pull_request`)
- suppression cycle import `ms.services.build <-> ms.output.errors` via module neutre `ms/services/build_errors.py`
- decomposition hotspot `auto.py` wave 1: factorisation des constructeurs `RepoReadiness` repetes (`_diag_blocker`, `_dist_blocker`)
- decomposition hotspot `service.py`: split prepare/publish via helpers de repo prep, body PR, merge wrapping, et version paths
- decomposition hotspot `auto.py` wave 2: split head-mode/carry-mode en helpers dedies, reduction de la profondeur conditionnelle
- subprocess directs: mapping AST hors tests + remplacement de `subprocess.check_output` dans `ms/services/dist.py` par `run_process`
- release CLI shared access checks: extraction `ensure_release_permissions_or_exit` + `print_current_release_user` dans `release_common.py`
- release app commands: extraction `_prepare_app_release` pour mutualiser le flux prepare/publish (request + PR creation)
- guided release (app/content): decomposition des etapes `confirm` en helpers (`validate`, `dispatch`, `open-control gate`)

Validation snapshot (post-iteration):

- `uv run pyright` -> `0 errors`
- `uv run pytest ms/test -q` -> `998 passed, 6 deselected`
- `uv run ruff check ms --select F` -> `All checks passed`
- `uv run ruff check ms` -> `All checks passed`
- `uv run ruff check ms --statistics` -> `0 issue`
- `grep -R "except Exception" ms` -> `0 match`
- Couverture timeout (calls directs wrappers subprocess):
  - `run_process`: `26/26`
  - `run_silent`: `23/23`
- Subprocess directs (`subprocess.run/check_output`, scan AST hors tests): `15 -> 14`
- Tests release ciblés:
  - `uv run pytest ms/test/cli/test_release_guided_flows.py -q` -> `4 passed`
  - `uv run pytest ms/test/services/test_release_* -q` -> `35 passed`
- Perf locale chaude:
  - `uv run ms check --no-strict` -> `1.245s`
  - `uv run ms status --no-copy` -> `0.321s`

Restant prioritaire immediat:

- reduction/justification des subprocess directs restants (`oc_cli`, `hardware`, `clipboard`, `checkers/common`)
- lot suivant de decomposition release cible sur sous-flux encore denses (si necessaire apres revue)
- decoupage complementaire release CLI: `release_content_commands.py` reste volumineux (~750 lignes), candidatable a split view/resolver/flow

---

## 10) Tracker execution (live)

Checkpoint courant (2026-02-07):

- A1 checksum bridge: DONE
- A2 timeouts/retry release: DONE
- A3 ecritures atomiques critiques: DONE
- A4 gates CI critiques: DONE
- B1 orchestration PR partagee app/dist: DONE (`pr_orchestration.py`)
- B2 cycle import `build <-> output.errors`: DONE (`build_errors.py`)
- B3 decomposition hotspots:
  - `auto.py` wave 1: DONE
  - `service.py` split prepare/publish: DONE
  - `auto.py` wave 2 (head/carry split): DONE
  - release CLI app/content guided confirm split: DONE
- B4 hardening exceptions/subprocess:
  - `except Exception`: DONE (`17 -> 0`)
  - subprocess directs restants: IN PROGRESS (`15 -> 14`, scan AST hors tests)

Regle de suivi:

- mise a jour du checkpoint a chaque lot termine
- publication syste matique: fichiers touches, tests lances, resultats, next actions numerotees

Dernier lot execute (2026-02-07, phase B3/B4):

- fichiers touches:
  - `ms/services/release/service.py`
  - `ms/services/release/auto.py`
  - `ms/services/dist.py`
  - `ms/cli/commands/release_common.py`
  - `ms/cli/commands/release_content_commands.py`
  - `ms/cli/commands/release_app_commands.py`
  - `ms/cli/release_guided_content.py`
  - `ms/cli/release_guided_app.py`
- resultats verification:
  - `uv run ruff check ms` -> `All checks passed`
  - `uv run pyright` -> `0 errors`
  - `uv run pytest ms/test -q` -> `998 passed, 6 deselected`
  - `uv run pytest ms/test/cli/test_release_guided_flows.py -q` -> `4 passed`
  - `uv run pytest ms/test/services/test_release_* -q` -> `35 passed`
- metriques:
  - hotspots release: `service.py` split DONE, `auto.py` wave 2 DONE
  - guided confirm steps: `_step_confirm` content `95 -> 43`, app `76 -> 38`
  - subprocess directs (`subprocess.run/check_output`, scan AST hors tests): `15 -> 14`
- prochaines actions:
  1. traiter les callsites subprocess restants par priorite risque/impact (oc_cli + hardware en premier)
  2. split complementaire de `release_content_commands.py` (view/resolver/flow) pour reduire la taille du module
  3. documenter les justifications pour les callsites volontairement conserves (wrappers platform/process)
  4. revalider ruff/pyright/pytest apres chaque lot
