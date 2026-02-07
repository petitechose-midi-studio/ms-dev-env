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

## 2.1) Regles anti-ambiguite (obligatoires)

Pour eviter toute interpretation, les regles suivantes sont strictes:

1. Un fichier n'est considere "migre" que si la logique metier a ete retiree du legacy et remplacee par delegation explicite.
2. Toute PR annonce clairement si elle est "no behavior change" ou "behavior change".
3. "No behavior change" impose des snapshots CLI/tests equivalents avant/apres.
4. Une PR ne melange pas extraction de structure et changement produit majeur.
5. Les shims legacy restent en place tant que l'item de scorecard correspondant n'est pas vert.
6. Toute exception de couche/import doit etre documentee dans la PR et retiree dans la wave suivante.

## 2.2) Hors scope explicite

Les sujets suivants ne font pas partie de ce programme, sauf decision explicite:

- redesign UX des commandes
- ajout de nouvelles features release non necessaires a la migration
- changement des politiques de publication (gates/protections) hors besoins techniques du refactor

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

PR-A9: extraction `resolve/plan_io` + `infra/artifacts/*` + `infra/open_control`

PR-A10: extraction `resolve/auto/*` + `flow/{permissions,ci_gate}` + reduction finale des imports legacy release

### 6.0) Tracking progression (live)

Snapshot date: 2026-02-07

- A1 (scaffold + architecture advisory): DONE
  - PR: https://github.com/petitechose-midi-studio/ms-dev-env/pull/35
  - Notes: baseline checkpoint merged in dedicated branch flow.

- A2 (domain extraction + shims): DONE
  - PR: https://github.com/petitechose-midi-studio/ms-dev-env/pull/36
  - Notes: `ms/release/domain/*` introduced; `ms/services/release/{model,config,semver,planner,errors}` now shims.

- A3 (infra GitHub extraction + shims): DONE
  - PR: https://github.com/petitechose-midi-studio/ms-dev-env/pull/37
  - Notes: `ms/release/infra/github/*` introduced; legacy GH modules preserved as compatibility wrappers.

- A4 (infra repos extraction + shared git ops): DONE
  - PR: https://github.com/petitechose-midi-studio/ms-dev-env/pull/38
  - Notes: introduced `ms/release/infra/repos/{git_ops,app,distribution}` and converted
    `ms/services/release/{app_repo,dist_repo}` into thin compatibility shims.
  - Verification: base branch `refactor/release-architecture-a4-infra-repos` synced local/remote on
    commit `0f6566e` before starting A5 work.

- A5 (content resolve/flow/view extraction): DONE
  - PR: https://github.com/petitechose-midi-studio/ms-dev-env/pull/39
  - Branch base: `refactor/release-architecture-a4-infra-repos`
  - Notes: extracted content path into `ms/release/{resolve,flow,view}` modules and
    rewired `ms/cli/commands/release_content_commands.py` to delegate orchestration.
  - Quality gate: strict typing cleanup done (no `Any`/unnecessary `cast`) and validated with:
    `uv run ruff check ...`, `uv run pyright ...`, `uv run pytest ms/test/services/test_release_*.py`
    `ms/test/cli/test_release_fsm.py ms/test/cli/test_release_guided_flows.py -q`.
  - Stack: PR #39 is opened on top of #38.

- A6 (app resolve/flow/view extraction): DONE
  - PR: https://github.com/petitechose-midi-studio/ms-dev-env/pull/40
  - Branch: `refactor/release-architecture-a6-app-flow`
  - Base strategy: stacked on A5 (`base PR #39`).
  - Scope delivered:
    - `ms/release/resolve/app_inputs.py`
    - `ms/release/flow/app_{plan,prepare,publish}.py`
    - `ms/release/view/app_console.py`
    - `ms/cli/commands/release_app_commands.py`
  - Behavior contract: no intentional behavior change; keep `ms release app ...` UX stable.
  - Pre-PR gate (completed):
    - `uv run ruff check ms/cli/commands/release_app_commands.py ms/release/resolve/app_inputs.py ms/release/flow/app_plan.py ms/release/flow/app_prepare.py ms/release/flow/app_publish.py ms/release/view/app_console.py`
    - `uv run pyright ms/cli/commands/release_app_commands.py ms/release/resolve/app_inputs.py ms/release/flow/app_plan.py ms/release/flow/app_prepare.py ms/release/flow/app_publish.py ms/release/view/app_console.py`
    - `uv run pytest ms/test/services/test_release_*.py ms/test/cli/test_release_fsm.py ms/test/cli/test_release_guided_flows.py -q`
  - Typing bar: no `Any`, no unnecessary `cast`, explicit contracts at layer boundaries.
  - Stack: PR #40 is opened on top of #39.

- A7 (guided split + sessions extraction): DONE
  - PR: https://github.com/petitechose-midi-studio/ms-dev-env/pull/41
  - Branch: `refactor/release-architecture-a7-guided-split`
  - Base strategy: stacked on A6 (`base PR #40`).
  - Scope delivered:
    - `ms/release/flow/guided/{fsm,sessions,bootstrap,app_steps,content_steps,router}.py`
    - `ms/release/view/guided_console.py`
    - compatibility shims:
      - `ms/cli/release_{fsm,guided,guided_app,guided_content,guided_common}.py`
      - `ms/services/release/wizard_session.py`
  - Behavior contract: no intentional behavior change; guided flow UX and command surface preserved.
  - Pre-PR gate (completed):
    - `uv run ruff check ms/cli/release_fsm.py ms/cli/release_guided_common.py ms/cli/release_guided_app.py ms/cli/release_guided_content.py ms/cli/release_guided.py ms/services/release/wizard_session.py ms/release/flow/guided/fsm.py ms/release/flow/guided/sessions.py ms/release/flow/guided/bootstrap.py ms/release/flow/guided/app_steps.py ms/release/flow/guided/content_steps.py ms/release/flow/guided/router.py ms/release/view/guided_console.py`
    - `uv run pyright ms/cli/release_fsm.py ms/cli/release_guided_common.py ms/cli/release_guided_app.py ms/cli/release_guided_content.py ms/cli/release_guided.py ms/services/release/wizard_session.py ms/release/flow/guided/fsm.py ms/release/flow/guided/sessions.py ms/release/flow/guided/bootstrap.py ms/release/flow/guided/app_steps.py ms/release/flow/guided/content_steps.py ms/release/flow/guided/router.py ms/release/view/guided_console.py`
    - `uv run pytest ms/test/services/test_release_*.py ms/test/cli/test_release_fsm.py ms/test/cli/test_release_guided_flows.py -q`
  - Typing bar: no `Any`, no unnecessary `cast`, explicit contracts at layer boundaries.
  - Stack: PR #41 is opened on top of #40.

- A8 (legacy shim reduction + architecture gates): DONE
  - PR: https://github.com/petitechose-midi-studio/ms-dev-env/pull/42
  - Branch: `refactor/release-architecture-a8-shim-reduction`
  - Base strategy: stacked on A7 (`base PR #41`).
  - Scope delivered:
    - reduced CLI usage of legacy `ms/services/release/*` shims in favor of
      `ms/release/{domain,infra,flow}` imports where equivalent modules exist.
    - removed `flow -> cli` coupling in guided release flow by introducing
      `ms/release/flow/guided/selection.py` and adapting CLI selector conversions.
    - switched CI architecture job from advisory to blocking in `.github/workflows/ci.yml`.
    - aligned architecture gates to current migration phase with bounded non-strict
      size caps for newly extracted guided modules.
  - Behavior contract: no intentional behavior change; CLI UX and release flow semantics preserved.
  - Pre-PR gate (completed):
    - `uv run ruff check ms/cli/commands/release_common.py ms/cli/commands/release_app_commands.py ms/cli/commands/release_content_commands.py ms/cli/release_guided_common.py ms/cli/release_guided_app.py ms/cli/release_guided_content.py ms/cli/release_guided.py ms/release/flow/guided/selection.py ms/release/flow/guided/app_steps.py ms/release/flow/guided/content_steps.py ms/release/flow/guided/router.py ms/test/architecture/_gate.py ms/test/architecture/test_module_size_limits.py`
    - `uv run pyright ms/cli/commands/release_common.py ms/cli/commands/release_app_commands.py ms/cli/commands/release_content_commands.py ms/cli/release_guided_common.py ms/cli/release_guided_app.py ms/cli/release_guided_content.py ms/cli/release_guided.py ms/release/flow/guided/selection.py ms/release/flow/guided/app_steps.py ms/release/flow/guided/content_steps.py ms/release/flow/guided/router.py ms/test/architecture/_gate.py ms/test/architecture/test_module_size_limits.py`
    - `uv run pytest ms/test/services/test_release_*.py ms/test/cli/test_release_fsm.py ms/test/cli/test_release_guided_flows.py -q`
    - `MS_ARCH_CHECKS=1 uv run pytest ms/test/architecture -q`
  - Typing bar: no `Any`, no unnecessary `cast`, explicit contracts at layer boundaries.
  - Stack: PR #42 is opened on top of #41.

- A9 (plan_io + artifacts + open_control extraction): DONE
  - PR: https://github.com/petitechose-midi-studio/ms-dev-env/pull/43
  - Branch: `refactor/release-architecture-a9-plan-artifacts-open-control`
  - Base strategy: stacked on A8 (`base PR #42`).
  - Scope delivered:
    - added `ms/release/resolve/plan_io.py`
    - added `ms/release/infra/open_control.py`
    - added `ms/release/infra/artifacts/{spec_writer,notes_writer,app_version_writer}.py`
    - converted legacy modules to compatibility shims:
      - `ms/services/release/{plan_file,open_control,spec,notes,app_version}.py`
    - rewired CLI imports to canonical modules in touched paths:
      - `ms/cli/commands/release_common.py`
      - `ms/cli/commands/release_content_commands.py`
      - `ms/cli/commands/release_app_commands.py`
      - `ms/cli/release_guided_common.py`
      - `ms/cli/release_guided_content.py`
  - Validation (completed):
    - `uv run ruff check ...` (edited files)
    - `uv run pyright ...` (edited files)
    - `uv run pytest ms/test/services/test_release_*.py ms/test/cli/test_release_fsm.py ms/test/cli/test_release_guided_flows.py -q`
    - `MS_ARCH_CHECKS=1 uv run pytest ms/test/architecture -q`
  - Typing bar: no `Any`, no unnecessary `cast`, explicit contracts at layer boundaries.
  - Stack: PR #43 is opened on top of #42.

- A10 (auto resolvers + ci/permissions flow extraction): DONE
  - PR: https://github.com/petitechose-midi-studio/ms-dev-env/pull/44
  - Branch: `refactor/release-architecture-a10-auto-ci-permissions`
  - Base strategy: stacked on A9 (`base PR #43`).
  - Scope delivered:
    - added `ms/release/resolve/auto/{diagnostics,strict,smart,head_mode,carry_mode}.py`
    - added `ms/release/flow/{permissions,ci_gate}.py`
    - converted `ms/services/release/auto.py` to compatibility shim
    - rewired `ms/services/release/service.py` access checks to delegate to release flow modules
    - reduced CLI legacy imports by switching auto/permission/ci usages to canonical modules in:
      - `ms/cli/commands/release_content_commands.py`
      - `ms/cli/commands/release_app_commands.py`
      - `ms/cli/release_guided_content.py`
      - `ms/cli/release_guided_app.py`
  - Validation (completed):
    - `uv run ruff check ...` (edited files)
    - `uv run pyright ...` (edited files)
    - `uv run pytest ms/test/services/test_release_*.py ms/test/cli/test_release_fsm.py ms/test/cli/test_release_guided_flows.py -q`
    - `MS_ARCH_CHECKS=1 uv run pytest ms/test/architecture -q`
  - Typing bar: no `Any`, no unnecessary `cast`, explicit contracts at layer boundaries.
  - Stack: PR #44 is opened on top of #43.

- B1 (build service split): DONE
  - PR: https://github.com/petitechose-midi-studio/ms-dev-env/pull/45
  - Branch: `refactor/release-architecture-b1-build-split`
  - Base strategy: stacked on A10 (`base branch refactor/release-architecture-a10-auto-ci-permissions`)
  - Scope delivered:
    - replaced monolith `ms/services/build.py` with package `ms/services/build/*`
    - introduced split modules: `_context`, `models`, `helpers`, `targets`, `runtime`, `service`
    - preserved import compatibility at `ms.services.build` via package `__init__.py`
    - updated `.gitignore` to unignore `ms/services/build/*` path explicitly
  - Validation (completed):
    - `uv run ruff check ...` (edited files)
    - `uv run pyright ...` (edited files)
    - `uv run pytest ms/test/cli -q`
    - `MS_ARCH_CHECKS=1 uv run pytest ms/test/architecture -q`
  - Typing bar: no `Any`, no unnecessary `cast`, explicit contracts at layer boundaries.
  - Next: start B2 (`services/toolchains.py` split).

- B2 (toolchains service split): DONE
  - PR: https://github.com/petitechose-midi-studio/ms-dev-env/pull/46
  - Branch: `refactor/release-architecture-b2-toolchains-split`
  - Base strategy: stacked on B1 (`base branch refactor/release-architecture-b1-build-split`)
  - Scope delivered:
    - replaced monolith `ms/services/toolchains.py` with package `ms/services/toolchains/*`
    - introduced split modules: `models`, `checksum`, `helpers`, `sync`, `service`, `_context`
    - preserved import compatibility at `ms.services.toolchains` via package `__init__.py`
    - preserved `ToolchainService` and `sha256_file` public imports used by CLI/tests
  - Validation (completed):
    - `uv run ruff check ...` (edited files)
    - `uv run pyright ...` (edited files)
    - `uv run pytest ms/test/services/test_toolchains_checksums.py -q`
    - `uv run pytest ms/test/cli -q`
    - `MS_ARCH_CHECKS=1 uv run pytest ms/test/architecture -q`
  - Typing bar: no `Any`, no unnecessary `cast`, explicit contracts at layer boundaries.
  - Next: start B3 (`services/repos.py` split).

- B3 (repos service split): DONE
  - PR: https://github.com/petitechose-midi-studio/ms-dev-env/pull/47
  - Branch: `refactor/release-architecture-b3-repos-split`
  - Base strategy: stacked on B2 (`base branch refactor/release-architecture-b2-toolchains-split`)
  - Scope delivered:
    - replaced monolith `ms/services/repos.py` with package `ms/services/repos/*`
    - introduced split modules: `models`, `manifest`, `git_ops`, `lockfile`, `sync`, `service`, `_context`
    - preserved import compatibility at `ms.services.repos` via package `__init__.py`
    - preserved `RepoService` public import used by CLI/setup/tests
  - Validation (completed):
    - `uv run ruff check ...` (edited files)
    - `uv run pyright ...` (edited files)
    - `uv run pytest ms/test/services/test_repos_service.py -q`
    - `uv run pytest ms/test/cli -q`
    - `MS_ARCH_CHECKS=1 uv run pytest ms/test/architecture -q`
  - Typing bar: no `Any`, no unnecessary `cast`, explicit contracts at layer boundaries.
  - Next: start B4 (`oc_cli/common.py` split).

- B4 (oc_cli common split): IN PROGRESS (LOCAL)
  - Branch: `refactor/release-architecture-b4-oc-cli-common-split`
  - Base strategy: start from merged B3 (`base branch refactor/release-architecture-b3-repos-split`)
  - Scope delivered locally:
    - replaced monolith `ms/oc_cli/common.py` with package `ms/oc_cli/common/*`
    - introduced split modules: `models`, `runtime`, `execution`, `output_parser`, `serial`, `__init__`
    - preserved import compatibility at `ms.oc_cli.common` (same public API exports)
    - updated architecture allowlists for relocated direct `rich`/`subprocess` usage
  - Validation (completed locally):
    - `uv run ruff check ...` (edited files)
    - `uv run pyright ...` (edited files)
    - `uv run pytest ms/test/oc_cli/test_common.py ms/test/services/test_hardware_service.py -q`
    - `uv run pytest ms/test/cli -q`
    - `MS_ARCH_CHECKS=1 uv run pytest ms/test/architecture -q`
  - Next: open PR-B4.

### 6.1) Ecart restant pour atteindre la cible release (post-B3 merged, B4 local)

Etat mesure sur la branche `refactor/release-architecture-b4-oc-cli-common-split`:

- Position stack Wave A: PR `#39` -> `#44` merged
- Progression lots long-terme:
  - lots merges: `13/19` (A1-A10 + B1 + B2 + B3)
  - lots en review: `0/19`
  - lot en cours local: `B4`
- Modules cibles release presents: `41/41`
- Modules cibles release manquants: `0`

Etat de trajectoire:

- Wave A est completement mergee.
- B1 est mergee avec compat import preservee et sans changement de comportement intentionnel.
- B2 est mergee avec le meme contrat de non-regression comportementale.
- B3 est mergee avec compat import preservee et sans changement de comportement intentionnel.
- B4 est demarree localement avec compat API preservee et sans changement de comportement intentionnel.
- Contrat migration conserve: `no behavior change`, typing stricte, shims de compat maintenus jusqu'au nettoyage final.

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

### 7.3 Snapshot courant (post-A10/B1/B2/B3 merged + B4 local, mesure locale)

Ces mesures completent la baseline historique et servent au pilotage des prochaines PR.

- `ms/services/release/*`: `22` fichiers, `1449` lignes totales
- Shims release approximatifs: `17` fichiers, `329` lignes
- Legacy release actif (hors shims): `5` fichiers, `1120` lignes
- Fichiers CLI important encore `ms.services.release.*`: `4` (4 points d'import)
- Modules legacy release importes par CLI: `2` (`ms.services.release.service`, `ms.services.release.remove`)
- Surface restante Wave B (hotspots): `486` lignes
  - `ms/services/hardware.py`: `173`
  - `ms/cli/commands/status.py`: `313`
- Build split B1 (decompose):
  - `ms/services/build/targets.py`: `210`
  - `ms/services/build/helpers.py`: `141`
  - `ms/services/build/runtime.py`: `110`
- Toolchains split B2 (decompose):
  - `ms/services/toolchains/helpers.py`: `236`
  - `ms/services/toolchains/sync.py`: `173`
  - `ms/services/toolchains/models.py`: `64`
- Repos split B3 (decompose):
  - `ms/services/repos/sync.py`: `141`
  - `ms/services/repos/manifest.py`: `107`
  - `ms/services/repos/git_ops.py`: `54`
- OC CLI common split B4 (decompose):
  - `ms/oc_cli/common/output_parser.py`: `220`
  - `ms/oc_cli/common/serial.py`: `98`
  - `ms/oc_cli/common/runtime.py`: `89`
- Estimation surface legacy restante connue (release actif + Wave B hotspots): `~1606` lignes

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

- Branche active actuelle: `refactor/release-architecture-b4-oc-cli-common-split`
- Wave A: PR `#39` -> `#44` merged
- Stack ouverte en review: aucune (pre-PR B4)
- Sequence execution recommandee pour rester sur la trajectoire:
  1. ouvrir PR-B4 (`oc_cli/common.py` split)
  2. demarrer PR-B5 (`services/hardware.py` split)
