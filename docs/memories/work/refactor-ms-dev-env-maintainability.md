# Refactor : maintenabilité de ms-dev-env — feuille de route d'exécution

**Scope** : dépôt Python `ms-dev-env` — **Status** : E4.2 et E4.3 Build qualifiés localement ; Repos/Toolchains et E4.4 restants — **Base initiale** : `75ec6eb` (main, 2026-09-26)
**Created** : 2026-09-26 — **Updated** : 2026-09-28
**Cap** : réduire le nombre d'endroits à comprendre/modifier pour changer un comportement. Corriger les contrats d'erreur avant de mutualiser ; sécuriser les parcours release avant de les restructurer.
**Hors périmètre** : `midi-studio`, `open-control`, `distribution`, `ms-manager` (voir `refactor-ms-product-maintainability.md`).

## Contexte vérifié (une ligne par fait)

- Config : `ms/cli/context.py:32` avale `Err` ; `get_int(...) or défaut` avale aussi `0` ; aucune plage ni type strict (`ms/core/config.py`).
- PlatformIO : `ms/core/platformio_runtime.py:74` code en dur `tools/platformio/venv` ; installation et check respectent `config.paths.tools`.
- États : `ms/tools/state.py` ne couvre ni `[]` (`AttributeError`) ni `OSError`/`UnicodeDecodeError` ; `session_store.py:35` ne couvre pas `UnicodeDecodeError`.
- Git : `ms/services/repos/git_ops.py:20` et `ms/release/infra/open_control.py:173` retournent « propre » sur erreur ; consommateur `repos/sync.py:105`.
- Résolution d'outils : `ms/tools/resolver.py` n'est importé que par ses tests ; build/tests passent par `ToolRegistry.get_bin_path` + `shutil.which`.
- Vestiges : `ms/cli/release_fsm.py` (seul son test l'importe) ; `Mode.ENDUSER` (aucun appel opérationnel) ; `ms dist` (schéma 1, aucun appelant trouvé).
- Structure : chaîne `BuildService → Runtime → Targets → Helpers → ContextBase` ; `unit_tests.py` 1210 l., `ux_workflows.py` 1002 l. ; adaptateur `_Deps` (`release_guided_app.py:32`) ; doublons `_base_env`/`_get_tool_path`/`_candidate_metadata_complete`/resolvers GitHub.
- Release ~53,6 % des lignes non vides (périmètre = `ms/release` + `ms/cli/*release*`, hors tests) ; sessions guidées mêlent données métier et curseurs UI (`idx_*`, `return_to_summary`).
- Tests release guidée : 95 `monkeypatch.setattr` dans `ms/test/cli/test_release_guided_flows.py`.
- Docs : `builds.yml` supprimé par `c78ef88` ; `INVARIANTS.md`/`HOW_TO_*` absents de `midi-studio/core/docs` ; archivage Desktop prescrit ; `code-style.md` se dit référence officielle.
- CI : contrôle de contrat sur `ms-manager@main` + dernière prerelease `distribution`, appelé par `ci.yml` et `integration.yml` sur PR ; `MS_ARCH_STRICT` transmis mais jamais lu (`MS_ARCH_CHECKS` est le verrou ; `_gate.py:15`).

## Décisions verrouillées (aucune question ouverte)

| Sujet | Décision | Règle de repli |
| --- | --- | --- |
| Ports | entier (rejeter bool) ou chaîne décimale ; plage **1–65535** ; `0` rejeté ; absent → défaut ; invalide → `ValueError` → `ConfigError` | `USER_ERROR` (1) au niveau CLI |
| Config CLI | fichier présent mais invalide/illisible → message + exit `USER_ERROR` ; absent → `None` en 1a, `Config()` en 1b | ne jamais retomber silencieusement sur un défaut |
| `load_state` | `Result[dict, StateError]` : absent/corrompu → `Ok({})` ; `OSError`/`UnicodeDecodeError` → `Err` ; consommateurs propagent `Err` (abandon + message), jamais traités comme « non installé » | `get_installed_version` → `Result[str|None, StateError]` |
| Session release | erreurs lecture/encodage/forme → `Err` ; schéma passe à **4** à l'ajout de `pending_op` ; schéma 3 → `Err` explicite | sessions courtes, pas de migration |
| Git dirty | `bool \| None` (`None` = inspection échouée) ; `sync` skip + warning ; `open_control` → blocage release | jamais d'opération sur état inconnu |
| PlatformIO | `resolve_platformio_runtime(start, *, tools_dir=None)` ; consommateurs qui ont la config passent `tools_dir` résolu ; défaut = `start`/workspace + `tools` | oc_cli/hardware gardent le défaut |
| `MS_ARCH_STRICT` | suppression (CI + `unit_tests.py` + test) | `MS_ARCH_CHECKS` conservé |
| `Mode.ENDUSER` | `gh search code` sur l'org ; 0 résultat → suppression ; sinon dépréciation | vérifier aussi `ms sync --tools --mode` |
| `ms dist` | `gh search code "ms dist"` + workflows `distribution` ; 0 → suppression commande+service+tests ; sinon `package` conservé, `manifest` schéma 1 retiré | décision consignée au journal |
| Resolver | migrer les tests vers `ToolRegistry.resolve_executable` puis supprimer `resolver.py` | interdiction de supprimer avant migration |
| CI contrat | PR = épinglé (commit `ms-manager` + tag `distribution`) dans `ci.yml` ; « dernière publication » = job planifié dans `integration.yml` ; doublon retiré ensuite | comparaison événements/permissions avant retrait |
| Docs | `builds.yml` → décrire `ci.yml` + `integration.yml` + workflows produit ; `INVARIANTS` → `CORE_ARCHITECTURE.md`/`ARCHITECTURE_REVIEW_RULES.md` ; `HOW_TO_*` → `INPUT_BINDINGS.md`/`CONTEXT_PRESENTATION.md`/`CC_LANE_FEATURE.md` ; `STATE_MANAGEMENT` → `CORE_ARCHITECTURE.md` ; Desktop → clôture Git/repo propriétaire | relire la cible avant substitution |

## Lots d'exécution (ordre imposé)

### E0 — Base (fait)

HEAD `75ec6eb`, `docs/README.md` modifié hors périmètre, passations non suivies.
Validation : `uv run pytest ms/test -q --ignore=ms/test/e2e` → **1216 passés, 14 skippés, 6 désélectionnés, 45,5 s**. Arch skippés par gate. Ruff/Pyright non rejoués.

### E1a — Fail-loud + régressions + docs rapides (1 PR, ~5 commits)

1. Config : `_port()` dans `ms/core/config.py` (absence/type/plage) ; `ms/cli/context.py` propage `Err` (`USER_ERROR`).
2. PlatformIO : paramètre `tools_dir` ; `build/helpers.py`, `checkers/tools.py` passent le répertoire résolu ; défaut inchangé ailleurs.
3. États : `load_state`/`get_installed_version` en `Result` (`state.py`, `helpers.py`, `sync.py`, `cli/commands/tools.py`) ; `read_session` → `except (OSError, ValueError)`.
4. Git : `_is_dirty` → `bool | None` dans `git_ops.py` + `open_control.py` ; `sync.py` skip fail-closed ; `bom.py`/`open_control_models.py` traitent `None` comme blocage.
5. Docs rapides : appliquer la table « Docs » ci-dessus.

Tests (rouges d'abord) : `test_config.py` (type, 0, -1, 70000, chaîne numérique, bool) ; **`ms/test/cli/test_context.py`** (invalide → exit 1 ; valide → config chargée ; absent → `None`) ; `test_state.py` (`[]`, non-UTF-8, `OSError` injecté, absent) ; tests session (`[]`, non-UTF-8, schéma inconnu) ; `test_repos_service.py` (git en échec → skip) ; `test_bom.py` (`dirty=None` → blocage).

Acceptation : cas d'erreur couverts, plus aucune continuation silencieuse, liens corrigés, suite complète verte.
Commandes : `uv run pytest ms/test/core ms/test/tools ms/test/release ms/test/cli ms/test/services -q` puis suite complète.

### E1b — Config canonique (1 PR)

`Config` non optionnel dans les services ; suppression des 7+ fallbacks (`base.py:38`, `prereqs.py:129`, `toolchains/models.py:59`, `check.py:86`, `checkers/workspace.py:150-162`, `bridge.py:301`, `bitwig.py:164`) ; absent → `Config()`.
Tests : contexte absent/valide ; un service représentatif avec `paths.*` personnalisés.

### E2 — Convergence des outils (1 PR)

`ToolRegistry.resolve_executable` (bundled puis PATH) ; `build/helpers._get_tool_path` et `unit_tests._get_tool_path` l'utilisent (erreurs propres à chaque service conservées) ; `toolchain_env.base_env(registry, workspace)` ; tests de `test_resolver.py` migrés vers le chemin réel ; suppression `resolver.py` + `release_fsm.py` (import du test redirigé vers `ms/release/flow/guided/fsm.py`) ; `MS_ARCH_STRICT` supprimé ; ENDUSER/`ms dist` traités selon la table de décisions (petites PR séparées si suppression).
Diff préalable obligatoire des deux resolvers GitHub ; mutualiser seulement si règles d'erreur identiques.

### E3 — Filet comportemental release + reprise (1 PR dédiée, avant E4)

Doubles : terminal (selectors/console), Git/GitHub (runner `gh`), stockage (session). Scénarios : happy, annulation/retour, échec PR, **reprise** (a) succès distant + échec `save_state`, (b) dispatch accepté + timeout client, (c) workflow en cours, (d) échec distant confirmé, (e) `main` a bougé entre dispatch et reprise. Assertions sur décisions/effets observables.

Correctif reprise : `pending_op` persisté **avant** dispatch (`request_id`, `repo`, `workflow`, `tag`, `source_sha`, `tooling_sha`, `at`) via `_dispatch_request_id` existant ; réconciliation à 4 états — `completed` (`release_exists_by_tag` + concordance), `in_flight` (run `pending/in_progress`), `failed` (conclusion `failure`), `undetermined` (attente bornée du marqueur `dispatch-<request_id>`, sinon erreur dédiée, **jamais** de rejeu ni de conversion en succès). Un `Err` ne devient un succès que si le résultat attendu est prouvé.
Fichiers : `guided/app_steps.py`, `app_confirm_step.py`, `app_release_dispatch.py`, `session_models.py`, `session_app_store.py`, `session_store.py` (+ contenu symétrique).

### E4 — Structure (après E3 pour tout parcours touché)

Plan métier immuable vs curseurs UI (`idx_*`/`return_to_summary` dérivés ou sous-objet) ; orchestrateur unique guidé/explicite ; réduction `_Deps` selon frontières réelles ; mixins build/repos/toolchains en composants explicites ; découpage `unit_tests.py`/`ux_workflows.py`. Un refactoring = une PR ; tests E3 inchangés (câblage des doubles libre).

### E5 — CI/doc (parallélisable dès E1a)

Contrôle épinglé PR / réel planifié (table décisions) ; suppression doublon après comparaison ; clôture documentaire (autorités uniques, plus d'archivage Desktop).

## Validation locale (matrice performante)

| Boucle | Commande | Attendu |
| --- | --- | --- |
| Ciblée (par commit) | `uv run pytest <fichiers> -q` | < 10 s |
| Lot E1 | `uv run pytest ms/test/core ms/test/tools ms/test/release ms/test/cli ms/test/services -q` | ~30 s |
| Complète hors e2e | `uv run pytest ms/test -q --ignore=ms/test/e2e` | ~45 s (baseline 1216 p.) |
| E2E local | `uv run pytest ms/test/e2e -q` | sans réseau |
| Arch (Windows) | `$env:MS_ARCH_CHECKS="1"; uv run pytest ms/test/architecture -q` | 6 tests |
| Lint / types | `uv run ruff check ms` ; `uv run pyright` | 0 erreur |

Règles : aucun réseau dans les boucles ciblée/complète (tests `network` désélectionnés par défaut) ; matériel jamais requis ; réseau uniquement à la demande (`-m network`, 3 tests). Suite complète avant clôture de PR.

## Journal d'avancement (1 ligne par étape, jamais réécrite)

Format : `date | lot | état | fichiers | preuve | note`

- 2026-09-26 | E0 | fait | — | pytest 1216p/14s/45,5s sur 75ec6eb | `docs/README.md` déjà modifié (hors périmètre)
- 2026-09-26 | E1a.1 | fait | `ms/core/config.py`, `ms/cli/context.py`, `ms/test/core/test_config.py`, `ms/test/cli/test_context.py` | 33 p. ciblés, ruff OK | ports 1–65535, `0` rejeté ; config invalide → exit USER_ERROR
- 2026-09-26 | E1a.2 | fait | `ms/core/platformio_runtime.py`, `build/helpers.py`, `checkers/tools.py`, `test_platformio_runtime.py` | 4 p., ruff OK | `tools_dir` explicite ; défaut `root/tools` inchangé
- 2026-09-26 | E1a.3b | fait | `session_store.py`, `test_guided_session_store.py` | 5 p. + 11 p. voisins, ruff OK | `except (OSError, ValueError)` ; encodage → `Err`
- 2026-09-26 | E1a.3a | fait | `state.py`, `toolchains/helpers.py`, `toolchains/sync.py`, `cli/commands/tools.py`, `test_state.py`, `test_integration_phase2.py` | 21 p. ciblés, ruff/pyright OK | API `Result` : corrompu → `Ok({})`, illisible → `Err` ; appelants propagent
- 2026-09-26 | E1a.4 | fait | `git_ops.py`, `repos/sync.py`, `open_control.py`, `open_control_models.py`, `bom.py`, `test_bom.py`, `test_repos_service.py` | 86 p. ciblés, pyright OK | `bool \| None` ; sync skip+warning ; `None` bloque le BOM
- 2026-09-26 | E1a.5 | fait | 7 docs (setup-architecture, onboarding, code-style, hw-navigation, tech-spec-modular, memories/README, implementation-plan) | grep résiduel = passation seulement | références mortes remplacées
- 2026-09-26 | E1a | fait | 16 fichiers source + 9 tests (+29 tests) | suite 1245p/14s/40s ; e2e 1p ; arch 6p ; ruff 0 ; pyright 0 | **non committé**
- 2026-09-26 | E1b | fait | 12 services + `cli/context.py` + 6 tests CLI | suite verte, ruff/pyright 0 | config normalisé en un point ; plus aucun fallback `config if ... else` ; `Config \| None` toléré uniquement en entrée de constructeur
- 2026-09-26 | E2 | fait | supprimés : `tools/resolver.py`, `cli/release_fsm.py`, `services/dist.py`, `commands/dist.py`, `Mode`/`ENDUSER`, `MS_ARCH_STRICT` ; ajoutés : `services/toolchain_env.py`, `release/flow/candidate_metadata.py`, `release/infra/github/ref_resolver.py` | suite 1225p/14s/55s ; e2e 1p ; arch 6p ; ruff 0 ; pyright 0 | `gh search` org : 0 usage externe ; -20 tests legacy retirés avec le code
- 2026-09-26 | E3 | fait (contrat renforcé) | idem + `test_release_resume.py` (20 tests) | scénario réel : dispatch → crash → rechargement disque → reprise sans re-dispatch ; suite verte | `completed` exige `request_id`+run (jamais la seule release) ; valeurs persistées utilisées ; recherche marqueur bornée injectable ; contenu symétrique ; préparation séparée du dispatch (aucun pending si préparation échoue/annulation)
- 2026-09-26 | E4.1 | fait (round-trip corrigé) | `session_app_store.py`, `session_content_store.py` : lecture du curseur imbriqué | app+contenu : sauvegarde→rechargement préserve curseur et `pending_op` | régression signalée en revue corrigée avec tests dédiés
- 2026-09-26 | E5 | fait | `integration.yml` : `schedule` hebdo ajouté | — | sur PR : seul le contrôle épinglé tourne ; setup/build integration restent exécutés sur PR ; contrôle « dernière publication » = main/planifié/dispatch
- 2026-09-26 | E4.0 | fait | caractérisation : catalogue unit-tests, découverte UX (`test_unit_tests.py`, `test_ux_workflows.py`) | — | prérequis posé avant extraction
- 2026-09-26 | E4.1 | fait | `session_models.py` (`SessionCursor`), stores app/content, `app_steps.py`, `content_steps.py`, `content_summary_step.py`, `content_candidates_step.py`, `content_confirm_step.py`, `notes_transition.py`, `test_guided_notes_transition.py` | suite 1239p/14s/44s ; e2e 1p ; arch 6p ; ruff 0 ; pyright 0 | sessions = plan + `step` + `pending_op` + `cursor` ; assertions E3 inchangées
- 2026-09-26 | E4.2 (étape 1) | fait | `contracts.py` (nouveau, `TerminalDependencies`), `app_contracts.py`, `content_contracts.py` : protocoles scindés terminal / stockage / opérations release, composés | pyright 0 ; 202 p. ciblés ; suite 1259+1 e2e ; arch 6p | `_Deps` inchangé (conformité structurelle) ; étape 2 : signatures d'étapes resserrées + réduction `_Deps`
- 2026-09-26 | E4.2 (étape 2)–E4.4 | restant | narrowing par étape, `_Deps` ; mixins build/repos/toolchains ; découpage `unit_tests.py`/`ux_workflows.py` | — | par PR séparée ; caractérisation en place
- 2026-09-26 | git | checkpoint | commit `2dd7d94` (travail en cours clairement identifié) | seul `docs/README.md` reste non suivi (préexistant) | suites post-revue : reprise 21 tests, round-trip app+contenu, scénario disque réel

- 2026-09-26 | E3 correction de revue | fait | identité/dispatch app, réconciliation, clôture app+contenu, stores, tests | 1260p/14s/6 désélectionnés ; arch 6p ; Ruff/Pyright 0 ; 32 tests reprise | commit `1e36135` ; prochaine étape : E4.2

## Reprise sans friction

### E4.3 — Build par composition (2026-09-28)

- Base locale `1b48e2e` (E4.2), lot Build uniquement. Les mixins Repos et Toolchains restent à migrer dans leurs propres lots.
- `ms/services/build/service.py` compose `BuildTargets` et `BuildRuntime` ; `targets.py` utilise explicitement `BuildPrerequisites` dans `helpers.py`. Le registre d'outils est partagé, la configuration normalisée par `BaseService` est transmise au runtime.
- Responsabilités : prérequis/outils/dépendances dans `helpers.py`, CMake et compilation dans `targets.py`, cycle de vie bridge/processus dans `runtime.py`, assemblage et API publique dans `service.py`. Les trois mixins et le contexte implicite `_context.py` sont supprimés.
- Les huit tests existants sont adaptés au propriétaire des prérequis. `ms/test/services/test_build_runtime.py` ajoute sept cas : fermeture du contexte bridge après erreur processus ou interruption en native/WASM, absence de lancement après échec de build, conflit HTTP/WebSocket.
- Qualification : `pytest ms/test -q` → **1268 passés, 14 skippés, 6 désélectionnés, 41,41 s** ; `MS_ARCH_CHECKS=1 pytest ms/test/architecture -q` → **6/6** ; Ruff et Pyright verts. Validation Python avec frontières processus simulées, sans nouvelle compilation produit réelle.
- Suite ordonnée : Repos, puis Toolchains (composition explicite et tests existants), puis E4.4 (`unit_tests.py`, `ux_workflows.py`). Rejouer pour chaque lot la suite complète, architecture, Ruff, Pyright et `git diff --check`. Publication de la pile locale et qualification CI toujours à traiter.

### E4.2 — Dépendances des étapes et réduction `_Deps` (2026-09-27)

- Branche `codex/guided-step-dependencies`, base locale `5aeb44f`. La publication distante de la pile Python antérieure reste à traiter séparément ; ce lot n'a pas poussé ces commits.
- `contracts.py`, `app_contracts.py`, `content_contracts.py` déclarent chaque signature d'effet une seule fois et composent les besoins des étapes. Les contrats complets `AppGuidedDependencies`/`ContentGuidedDependencies` ne sont utilisés que par les deux orchestrateurs `*_steps.py`.
- Notes → menu uniquement ; résumé Content → menu + inspection BOM ; BOM → inspection/présentation/promotion ; candidats → plan/inspection/préparation ; préparation → candidat/PR/présentation ; publication → dispatch/clôture. Confirmation conserve les effets requis pour persister l'intention, publier et réconcilier, sans bootstrap ni menus de configuration.
- `ms/cli/release_guided_app.py` et `release_guided_content.py` lient directement les fonctions métier via `staticmethod` et le contexte de session via `partial`, au moment de l'appel. Les wrappers de transmission d'arguments sont supprimés ; l'adaptateur de promotion garde son contrôle de permission effectif. `GuidedCliTerminal` remplace `GuidedCliDependencies` et n'expose plus le contrôle CI.
- Câblage des doubles CLI déplacé au propriétaire du contrôle CI ; assertions des parcours de reprise inchangées. Sonde temporaire Pyright : refus des trois effets hors contrat (Notes→clear, Résumé→promotion BOM, Publication→bootstrap), puis sonde supprimée.
- Régression trouvée : Start depuis le résumé Content sans tag transmettait encore `idx_summary`/`return_to_summary` à la session et levait `TypeError`. `test_guided_content_summary.py` rouge avant correction, vert après migration vers `session.cursor`.
- Qualification : `pytest ms/test -q` → **1261 passés, 14 skippés, 6 désélectionnés, 38,75 s**, E2E local inclus ; `MS_ARCH_CHECKS=1 pytest ms/test/architecture -q` → **6/6** ; Ruff/Pyright **0 erreur** ; `git diff --check` propre. Aucun dispatch de release réelle.
- Suite ordonnée : **E4.3**, remplacer les mixins build/repos/toolchains par composants explicites après lecture de leurs tests de caractérisation ; **E4.4**, extraire les responsabilités de `unit_tests.py` et `ux_workflows.py`. Un lot par changement, même matrice de validation ; pas de refactoring dicté par un nombre de lignes.

### Relecture de l'historique local (2026-09-27)

- `0733c06177bd1f5434ce7ea72ff8a609a90195a8` relu : extraction des protocoles terminal/stockage/opérations et composition des contrats App/Content. Il réalise E4.2 étape 1 ; les signatures des étapes et `_Deps` restent à resserrer. Cette relecture n'est pas une nouvelle qualification d'exécution.
- Dans l'historique présent, le correctif reprise est `54e2c5f` ; les mentions historiques de `1e36135` ci-dessous ne sont pas le SHA à utiliser pour reprendre. La racine contient plusieurs commits locaux non publiés ; ne pas les pousser comme simple accompagnement des promotions produit.
- Revalidation ciblée après relecture : `pytest ms/test/cli/test_release_guided_flows.py ms/test/release/test_release_resume.py -q` → **38 passés en 1,44 s**. Aucun changement Python dans cette continuation produit.

### Correction de revue — reprise release (2026-09-26, après `2dd7d94`)

- **Identité effective** : le dispatcher app calcule l'identité avec le SHA issu de la préparation/fusion et les inputs réellement envoyés. Il appelle `before_dispatch` pour persister l'intention après le traitement du candidat (et son attente si demandée), avant le dispatch release. Un échec du candidat ou de cette écriture ne déclenche pas la release.
- **Preuve de reprise** : les sessions app/contenu conservent `pending_inputs`. La réconciliation vérifie la cohérence tag/source/tooling, le type d'événement, le chemin du workflow et le hash de requête recalculé sur le `head_sha` du run historique. Elle exige ensuite succès du run et présence de la release. Elle ne recalcule pas l'identité à partir du `main` courant. Cette preuve s'appuie sur le contrat du workflow producteur ; elle ne remplace pas la vérification cryptographique des artefacts.
- **Compatibilité** : une ancienne intention de schéma 4 sans `pending_inputs` reste lisible mais ne permet pas de déclarer la publication terminée ; réconciliation `undetermined`, sans rejeu automatique.
- **Clôture durable** : les deux parcours suppriment la session après réconciliation `completed`. Une erreur de suppression est propagée ; l'intention reste disponible pour une nouvelle tentative de clôture.
- **Preuves locales nouvelles** : SHA fusionné différent du SHA de départ ; vrai dispatch interrompu après acceptation distante ; timeout après acceptation ; échec de suppression après succès ; rechargement disque puis vraie réconciliation avec `main` déplacé ; identités source/tooling/head/workflow discordantes ; candidat en échec sans intention release ; persistance refusée sans dispatch release ; clôture contenu sur disque ; marqueur retardé avec attente simulée.
- **Validation exécutée** : `pytest ms/test` → **1260 passés, 14 skippés, 6 désélectionnés en 47,47 s**, E2E local inclus ; architecture activée → **6 passés** ; Ruff/Pyright → **0 erreur** ; `git diff --check` sans erreur. Tests reprise → **32 passés en 0,44 s**, sans réseau réel ni délai d'attente réel de réconciliation. Aucun workflow distant n'a été lancé pour cette validation.
- **État de livraison** : correctif intégré au commit `1e36135`. Hors commit : `docs/README.md` (préexistant, périmètre utilisateur) et la passation produit `refactor-ms-product-maintainability.md` (autre périmètre). Checkpoints : `2dd7d94` puis `1e36135`.

1. Lire le **Journal** (dernière ligne = point de départ) et la table **Décisions**.
2. Lancer la commande de la **matrice** correspondant au lot en cours.
3. Ne modifier que la ligne du journal concernée ; garder 1 ligne par étape ; consigner blocage plutôt qu'improviser.
