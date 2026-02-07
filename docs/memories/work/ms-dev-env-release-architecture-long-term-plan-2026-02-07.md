# Plan long terme - refactor architecture release (ms)

Status: ACTIVE MEMORY (LONG TERM)

Date: 2026-02-07

Owner: ms maintainers

Dedicated branch: `refactor/release-architecture-long-term`

Scope: `ms` package (priorite release), avec rollout progressif en PRs courtes.

---

## 1) Intentions et decision

Ce refactor est valide et va dans la bonne direction.

Objectif principal: separer strictement les responsabilites release en 3 couches independantes:

- `view` (affichage)
- `flow` (orchestration)
- `resolve` (resolution/validation des inputs)

Objectif secondaire: reduire la dette structurelle sur les hotspots transverses (`build`, `toolchains`, `repos`, `oc_cli`, `status`) apres stabilisation release.

Principe de pilotage: **safe migration first** (compat CLI + shims) puis simplification interne.

---

## 2) Strategie de branche et cadence PR

Branche de reference long terme:

- `refactor/release-architecture-long-term`

Mode de livraison:

1. PRs progressives, petites, mergeables seules.
2. Une PR = un objectif technique principal + metriques avant/apres.
3. Pas de big-bang.
4. Compatibilite CLI maintenue jusqu'au retrait explicite des shims.

Convention PR:

- Prefix: `refactor(release): ...` puis `refactor(services): ...`
- Taille cible: <= 600 lignes nettes modifiees (soft limit)
- Fichiers cibles: limiter le rayon de changement par PR

---

## 3) Treeview cible long terme

```text
ms/
  __main__.py

  cli/
    app.py
    context.py
    commands/
      build_cmd.py
      run_cmd.py
      web_cmd.py
      upload_cmd.py
      monitor_cmd.py
      check.py
      prereqs.py
      setup.py
      sync.py
      tools.py
      clean.py
      wipe.py
      workspace.py
      status.py
      release/
        root.py
        content.py
        app.py
        guided.py
    presenters/
      status_rich.py
      status_plain.py
      common.py

  release/
    contracts.py
    errors.py

    domain/
      config.py
      models.py
      semver.py
      planner.py

    resolve/
      common.py
      plan_io.py
      content_inputs.py
      app_inputs.py
      auto/
        diagnostics.py
        strict.py
        smart.py
        head_mode.py
        carry_mode.py

    flow/
      permissions.py
      ci_gate.py
      content_plan.py
      content_prepare.py
      content_publish.py
      content_remove.py
      app_plan.py
      app_prepare.py
      app_publish.py
      guided/
        fsm.py
        bootstrap.py
        content_steps.py
        app_steps.py
        sessions.py

    view/
      urls.py
      content_console.py
      app_console.py
      guided_console.py

    infra/
      github/
        client.py
        ci.py
        workflows.py
        pr_merge.py
      repos/
        git_ops.py
        distribution.py
        app.py
      artifacts/
        spec_writer.py
        notes_writer.py
        app_version_writer.py
      open_control.py

  services/
    build/
      service.py
      native.py
      wasm.py
      runtime.py
      prereqs.py
      tool_resolution.py
      errors.py
    toolchains/
      service.py
      platformio.py
      jdk.py
      wrappers.py
      checksums.py
    repos/
      service.py
      manifest.py
      sync.py
      lockfile.py
    check/
      service.py
    hardware/
      service.py
      oc_adapter.py

  oc_cli/
    runtime.py
    execution.py
    output_parser.py
    serial.py
    oc_build.py
    oc_upload.py
    oc_monitor.py
    common.py   # shim temporaire

  core/
  git/
  platform/
  output/
  tools/

  test/
    architecture/
      test_release_layering.py
      test_import_layers.py
      test_module_size_limits.py
      test_subprocess_policy.py
      test_rich_usage_policy.py
```

---

## 4) Regles de dependances (non negotiables)

Direction des imports (release):

- `cli.commands.release.*` -> `release.resolve|flow|view`
- `release.resolve.*` -> `release.domain.*` (+ infra read-only explicitement autorisee)
- `release.flow.*` -> `release.resolve|domain|infra`
- `release.view.*` -> `release.contracts|output.console` uniquement
- Interdit: `view -> flow`, `view -> infra`, `flow -> typer/rich`

Regles globales:

- `services/*` n'importe jamais `cli/*`
- subprocess passe par `ms/platform/process.py`, sauf allowlist documentee
- pas de cycle import non documente

---

## 5) Mapping des hotspots actuels vers la cible

### 5.1 Release CLI et guided

- `ms/cli/commands/release_content_commands.py` (748) ->
  - `ms/cli/commands/release/content.py` (facade Typer)
  - `ms/release/resolve/content_inputs.py`
  - `ms/release/flow/content_plan.py`
  - `ms/release/flow/content_prepare.py`
  - `ms/release/flow/content_publish.py`
  - `ms/release/flow/content_remove.py`
  - `ms/release/view/content_console.py`

- `ms/cli/commands/release_app_commands.py` (480) ->
  - `ms/cli/commands/release/app.py`
  - `ms/release/resolve/app_inputs.py`
  - `ms/release/flow/app_plan.py`
  - `ms/release/flow/app_prepare.py`
  - `ms/release/flow/app_publish.py`
  - `ms/release/view/app_console.py`

- `ms/cli/release_guided_content.py` (516) ->
  - `ms/release/flow/guided/content_steps.py`
  - `ms/release/view/guided_console.py`

- `ms/cli/release_guided_app.py` (436) ->
  - `ms/release/flow/guided/app_steps.py`
  - `ms/release/view/guided_console.py`

- `ms/cli/release_fsm.py` -> `ms/release/flow/guided/fsm.py`
- `ms/cli/release_guided_common.py` -> `ms/release/flow/guided/bootstrap.py`
- `ms/services/release/wizard_session.py` -> `ms/release/flow/guided/sessions.py`

### 5.2 Release service/core orchestration

- `ms/services/release/service.py` (692) ->
  - `ms/release/flow/permissions.py`
  - `ms/release/flow/ci_gate.py`
  - `ms/release/flow/content_*`
  - `ms/release/flow/app_*`

- `ms/services/release/auto.py` (778) ->
  - `ms/release/resolve/auto/diagnostics.py`
  - `ms/release/resolve/auto/strict.py`
  - `ms/release/resolve/auto/smart.py`
  - `ms/release/resolve/auto/head_mode.py`
  - `ms/release/resolve/auto/carry_mode.py`

### 5.3 Release infra

- `ms/services/release/gh.py` -> `ms/release/infra/github/client.py`
- `ms/services/release/ci.py` -> `ms/release/infra/github/ci.py`
- `ms/services/release/workflow.py` -> `ms/release/infra/github/workflows.py`
- `ms/services/release/pr_orchestration.py` -> `ms/release/infra/github/pr_merge.py`
- `ms/services/release/app_repo.py` -> `ms/release/infra/repos/app.py`
- `ms/services/release/dist_repo.py` -> `ms/release/infra/repos/distribution.py`
- shared git ops (duplication app/dist) -> `ms/release/infra/repos/git_ops.py`
- `ms/services/release/spec.py` -> `ms/release/infra/artifacts/spec_writer.py`
- `ms/services/release/notes.py` -> `ms/release/infra/artifacts/notes_writer.py`
- `ms/services/release/app_version.py` -> `ms/release/infra/artifacts/app_version_writer.py`
- `ms/services/release/open_control.py` -> `ms/release/infra/open_control.py`

### 5.4 Domain release

- `ms/services/release/model.py` -> `ms/release/domain/models.py`
- `ms/services/release/config.py` -> `ms/release/domain/config.py`
- `ms/services/release/semver.py` -> `ms/release/domain/semver.py`
- `ms/services/release/planner.py` -> `ms/release/domain/planner.py`
- `ms/services/release/errors.py` -> `ms/release/errors.py`
- `ms/services/release/plan_file.py` -> `ms/release/resolve/plan_io.py`

---

## 6) Plan PR progressif (long terme)

## Wave A - Release bounded context (priorite absolue)

PR-A1: scaffold `ms/release/*` + contracts/errors + regles import (tests architecture en warning)

PR-A2: extraction `domain` pure (models/config/semver/planner)

PR-A3: extraction `infra/github` (gh/ci/workflow/pr) sans changement fonctionnel

PR-A4: extraction `infra/repos` + `git_ops` shared (app/dist)

PR-A5: extraction `resolve/content_inputs` + `flow/content_*` + `view/content_console`

PR-A6: extraction `resolve/app_inputs` + `flow/app_*` + `view/app_console`

PR-A7: guided split (`flow/guided/*` + `view/guided_console`) + sessions

PR-A8: reduction shims legacy release + architecture tests en mode bloquant

## Wave B - Services transverses

PR-B1: split `services/build.py` -> `services/build/*`

PR-B2: split `services/toolchains.py` -> `services/toolchains/*`

PR-B3: split `services/repos.py` -> `services/repos/*`

PR-B4: split `oc_cli/common.py` -> `oc_cli/runtime|execution|output_parser|serial`

PR-B5: `services/hardware.py` via adapter `oc_adapter.py` + reduction subprocess directs

PR-B6: `cli/status` extraction presenters + alignement `ConsoleProtocol`

## Wave C - Nettoyage final

PR-C1: suppression des shims devenus inutiles

PR-C2: documentation contributors + ADR architecture + playbook migrations

PR-C3: verrouillage CI final (architecture + guardrails taille/complexite)

---

## 7) Metriques de qualite (baseline -> cible)

Baseline (snapshot valide 2026-02-07):

- `uv run pyright` -> 0 errors
- `uv run pytest ms/test -q` -> 998 passed, 6 deselected
- `uv run ruff check ms` -> 0 issue
- cycles imports non triviaux: 0
- subprocess directs hors tests (run/check_output): 14
- duplication app_repo/dist_repo (similarite): ~0.806

Hotspots taille (lignes):

- `ms/cli/commands/release_content_commands.py`: 748
- `ms/cli/commands/release_app_commands.py`: 480
- `ms/cli/release_guided_content.py`: 516
- `ms/cli/release_guided_app.py`: 436
- `ms/services/release/service.py`: 692
- `ms/services/release/auto.py`: 778

### 7.1 Scorecard obligatoire

| ID | Metrique | Baseline | Cible Wave A | Cible finale |
|---|---|---:|---:|---:|
| ARC-01 | Violations de couches release (tests architecture) | N/A | 0 | 0 |
| ARC-02 | Cycles imports non triviaux | 0 | 0 | 0 |
| ARC-03 | Max lignes module release | 778 | <= 350 | <= 250 |
| ARC-04 | Modules release > 400 lignes | 6 | <= 2 | 0 |
| ARC-05 | Similarite `app_repo` vs `dist_repo` | 0.806 | <= 0.50 | <= 0.35 |
| REL-01 | Subprocess directs hors allowlist | 14 | <= 10 | <= 5 |
| QLT-01 | `pyright` errors | 0 | 0 | 0 |
| QLT-02 | `ruff check ms` issues | 0 | 0 | 0 |
| QLT-03 | `pytest ms/test -q` failures | 0 | 0 | 0 |
| TST-01 | Tests architecture dedies | 0 | >= 5 | >= 10 |

### 7.2 Commandes de mesure standard

```bash
uv run pyright
uv run ruff check ms
uv run pytest ms/test -q
```

Mesures architecture (a ajouter et faire tourner en CI):

```bash
uv run pytest ms/test/architecture -q
```

Mesure hotspots (script guardrail simple):

```bash
python - <<'PY'
from pathlib import Path
targets = [
    "ms/cli/commands/release_content_commands.py",
    "ms/cli/commands/release_app_commands.py",
    "ms/cli/release_guided_content.py",
    "ms/cli/release_guided_app.py",
    "ms/services/release/service.py",
    "ms/services/release/auto.py",
]
for t in targets:
    p = Path(t)
    if p.exists():
        print(f"{t}: {sum(1 for _ in p.open('r', encoding='utf-8'))}")
PY
```

---

## 8) CI enforcement cible

Gates bloquants:

1. `pyright`
2. `ruff check ms`
3. `pytest ms/test -q`
4. `pytest ms/test/architecture -q`

Guardrails additionnels (bloquants apres Wave A):

- violation imports couches release -> fail
- module release > 400 lignes -> fail (puis > 300 en cible finale)
- subprocess direct hors allowlist -> fail

---

## 9) Risques et strategie rollback

Risque R1: regression UX CLI release

- Mitigation: garder facades Typer stables + tests CLI existants + snapshots guided.

Risque R2: complexite de migration import

- Mitigation: shims temporaires, deprecation progressive, suppression en Wave C seulement.

Risque R3: sur-fragmentation OSS

- Mitigation: limiter profondeur des packages; preferer "feature slices" coherentes.

Rollback operationnel:

- rollback PR par PR (pas de batch)
- aucun changement irreversible infra/prod dans ce plan
- conserver chemins legacy tant que les tests architecture ne sont pas stables

---

## 10) Template de reporting par PR

Chaque PR doit reporter:

1. objectif et perimetre
2. fichiers deplaces/crees/supprimes
3. compatibilite (CLI/import)
4. metriques avant/apres (tableau scorecard)
5. commandes de validation executees
6. risques restants + next PR proposee

---

## 11) Exit criteria du programme

Le programme est considere termine quand:

- separation `view/flow/resolve` est effective et testee
- hotspots release sont decomposes sous les seuils cible
- shims legacy release sont retires
- subprocess directs restants sont justifies ou migres
- CI bloque toute regression d'architecture
- documentation contributors est a jour

---

## 12) Notes operationnelles immediate

- Branche dediee creee: `refactor/release-architecture-long-term`
- Prochaine action recommandee: ouvrir PR-A1 (scaffold + tests architecture non bloquants)
