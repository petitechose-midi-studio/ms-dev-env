# Recon Validation + Plan Main (2026-02-16)

## Objectif

Verifier que les constats de reconnaissance sont bien fondes, puis fixer un plan d'implementation executable sur `main` avec:

- commits logiques et lisibles,
- gate build/test a chaque etape,
- sequence de review finale avant le premier changement de code fonctionnel.

## Methode de validation

Validation refaite a partir du code source et de la doc (pas d'hypothese non verifiee):

- `midi-studio/core`
- `midi-studio/plugin-bitwig`
- `open-control/framework`
- `open-control/note`
- `docs/memories/work/feature-ms-sequencer/*`

Commandes de verification executees:

- `pio run -e dev` dans `midi-studio/core` -> SUCCESS
- `pio run -e dev` dans `midi-studio/plugin-bitwig` -> SUCCESS
- `pio test -e native` dans `open-control/note` -> ECHEC build sur 3 tests (`test_clock`, `test_engine`, `test_smoke`)

## Validation des constats (preuves)

### 1) Separation Handler -> State -> View

Statut: **CONFIRME (positif)**.

- Les handlers sequencer ecrivent l'etat sans appels LVGL directs:
  - `midi-studio/core/src/handler/sequencer/SequencerStepHandler.cpp`
  - `midi-studio/core/src/handler/sequencer/SequencerMacroPropertyHandler.cpp`
  - `midi-studio/core/src/handler/sequencer/SequencerStepEditHandler.cpp`
- Le rendu est bien concentre dans les vues:
  - `midi-studio/core/src/ui/view/SequencerView.cpp`
  - `midi-studio/core/src/context/StandaloneContext.cpp` (rendu overlays)

Impact: base saine pour iterer sans rearchitecture lourde.

### 2) Mutations step dispersees + revision manuelle

Statut: **CONFIRME (risque maintenabilite)**.

- Ecritures directes sur `note/velocity/gate` dans plusieurs handlers:
  - `midi-studio/core/src/handler/sequencer/SequencerMacroPropertyHandler.cpp`
  - `midi-studio/core/src/handler/sequencer/SequencerStepEditHandler.cpp`
- Increments manuels de `stepDataRevision`:
  - `midi-studio/core/src/handler/sequencer/SequencerMacroPropertyHandler.cpp`
  - `midi-studio/core/src/handler/sequencer/SequencerStepEditHandler.cpp`

Impact: duplication des regles metier, risque d'oublis lors d'evolutions.

### 3) Duplication de la logique pagination/index

Statut: **CONFIRME**.

- Formule repetee `(len + stepsPerPage - 1) / stepsPerPage` dans:
  - `midi-studio/core/src/handler/sequencer/SequencerStepHandler.cpp`
  - `midi-studio/core/src/handler/sequencer/SequencerMacroPropertyHandler.cpp`
  - `midi-studio/core/src/handler/sequencer/SequencerStepEditHandler.cpp`
  - `midi-studio/core/src/context/StandaloneContext.cpp`
  - `midi-studio/core/src/ui/view/SequencerView.cpp`

Impact: risque de divergence de comportement si une formule evolue localement.

### 4) Mapping encodeur OPT incoherent (constantes magiques)

Statut: **CONFIRME**.

- Valeurs discretes `255` et `191` uniquement ici:
  - `midi-studio/core/src/context/StandaloneContext.cpp`
- Le reste du code suit plutot des gammes explicites (ex: 128, gateMax+1):
  - `midi-studio/core/src/handler/sequencer/SequencerStepEditHandler.cpp`

Impact: comportement difficile a raisonner et a maintenir.

### 5) Overlays `SEQ_SETTINGS` et `SEQ_TRACK_CONFIG` partiels

Statut: **CONFIRME**.

- Types declares:
  - `midi-studio/core/src/ui/OverlayTypes.hpp`
- Signaux enregistres:
  - `midi-studio/core/src/state/CoreState.hpp`
- Aucune ouverture/handler/rendu relies a ces overlays dans `core/src/*`.

Impact: surface API exposee sans flux fonctionnel complet.

### 6) Autorite input: contrat strict partiellement cable

Statut: **CONFIRME AVEC NUANCE**.

- `AuthorityResolver` supporte overlay + active view:
  - `open-control/framework/src/oc/core/input/AuthorityResolver.hpp`
- `OverlayManager` ne renseigne que l'overlay provider:
  - `open-control/framework/src/oc/context/OverlayManager.hpp`
- Aucun usage trouve de `setActiveViewProvider(...)` dans `core`/`plugin-bitwig`.
- Nuance importante: les scopes LVGL incluent un predicat `isActive` base sur `LV_OBJ_FLAG_HIDDEN`:
  - `open-control/ui-lvgl/src/oc/ui/lvgl/Scope.hpp`

Conclusion nuancee: ce n'est pas un bug frontal dans l'etat actuel, mais le contrat "exactement une autorite" est moins explicite qu'annonce dans les invariants.

### 7) Divergence docs vs runtime (defaults)

Statut: **CONFIRME**.

- Runtime (`oc-note`) :
  - `DEFAULT_LENGTH = 8`
  - `DEFAULT_STEPS_PER_BEAT = 2` (1/8)
  - dans `open-control/note/src/oc/note/sequencer/StepSequencerState.hpp`
- Docs memoires indiquent encore du 1/16 et/ou longueur 18 dans plusieurs plans:
  - `docs/memories/work/feature-ms-sequencer/tech-spec.md`
  - `docs/memories/work/feature-ms-sequencer/implementation-plan-v0-framework.md`

Impact: confusion produit/technique, reviews plus lentes.

### 8) Incoherence mineure transport scope

Statut: **CONFIRME**.

- Champ `transport_scope_element_` stocke dans le handler:
  - `midi-studio/core/src/handler/transport/TransportHandler.hpp`
- Binding PLAY/STOP en global (sans scope):
  - `midi-studio/core/src/handler/transport/TransportHandler.cpp`

Impact: dette de lisibilite (intention vs implementation).

### 9) BootContext bypass temporaire

Statut: **CONFIRME**.

- Commentaire explicite "Skip BootContext for now - debug crash":
  - `midi-studio/core/main.cpp`

Impact: dette technique assumee, a tracer dans le plan.

### 10) Couverture tests/CI insuffisante pour le sequencer

Statut: **CONFIRME**.

- Pas de dossier `test/` dans `core` ni `plugin-bitwig`.
- CI `core` et `plugin-bitwig` orientee build firmware, pas de tests metier sequencer:
  - `midi-studio/core/.github/workflows/ci.yml`
  - `midi-studio/plugin-bitwig/.github/workflows/ci.yml`
- `open-control/note` a des tests natifs mais en echec de build actuellement.

Impact: risque de regressions silencieuses.

## Plan complet d'implementation (branche `main`, commits progressifs)

## Regles d'execution

- Travail sur `main` (demande explicite).
- Commits atomiques, un objectif clair par commit.
- Gate build/test a chaque etape.
- Si un gate echoue, correction immediate avant etape suivante.

### Gate standard a chaque etape

1. `pio run -e dev` dans `midi-studio/core` (bloquant)
2. `pio run -e dev` dans `midi-studio/plugin-bitwig` (bloquant)
3. `pio test -e native` dans `open-control/note` (non bloquant au debut tant que la dette test n'est pas corrigee, mais resultat trace)

## Phase A - Stabiliser les invariants core sequencer

### Etape A1 - Centraliser les mutations step

But:

- Introduire un chemin unique de mutation step (note/velocity/gate) avec revision bump integre.

Fichiers cibles:

- `midi-studio/core/src/state/sequencer/SequencerState.hpp`
- `midi-studio/core/src/handler/sequencer/SequencerMacroPropertyHandler.cpp`
- `midi-studio/core/src/handler/sequencer/SequencerStepEditHandler.cpp`

Commit cible:

- `refactor(sequencer): centralize step mutations and revision updates`

Definition of done:

- Plus de bump manuel disperse dans les handlers touches.
- Comportement fonctionnel identique cote UI.

### Etape A2 - Extraire utilitaire pagination/index

But:

- Supprimer les formules dupliquees et unifier pageCount/page/index absolu.

Fichiers cibles:

- `midi-studio/core/src/handler/sequencer/*`
- `midi-studio/core/src/ui/view/SequencerView.cpp`
- `midi-studio/core/src/context/StandaloneContext.cpp`

Commit cible:

- `refactor(sequencer): extract shared paging/index helpers`

Definition of done:

- Une seule source de verite pour la pagination active.

### Etape A3 - Normaliser contrat encodeurs sequencer

But:

- Remplacer `255/191` par des conventions explicites coherentes (NOTE/VEL=128, GATE=MAX+1).

Fichiers cibles:

- `midi-studio/core/src/context/StandaloneContext.cpp`
- `midi-studio/core/src/handler/sequencer/SequencerInputUtils.hpp`

Commit cible:

- `fix(sequencer): normalize encoder discrete mapping contract`

Definition of done:

- Plus de constantes magiques.
- Sync macro/OPT coherent entre handler et contexte.

## Phase B - Autorite input et overlays

### Etape B1 - Verrouiller la regle d'autorite

But:

- Rendre explicite la priorite overlay > vue active > global, en conservant les scopes LVGL existants.

Options techniques (recommandee en premier):

- Ajouter un provider de vue active au resolver (ou equivalent custom layer), branche depuis le contexte.

Fichiers cibles:

- `open-control/framework/src/oc/context/OverlayManager.hpp` (si extension retenue)
- `midi-studio/core/src/context/StandaloneContext.cpp`
- `midi-studio/plugin-bitwig/src/context/BitwigContext.cpp`

Commit cible:

- `feat(input): wire explicit active-view authority provider`

Definition of done:

- Regle d'autorite lisible dans le code, pas seulement implicite via visibilite.

### Etape B2 - Finaliser ou fermer proprement les overlays plans

But:

- Soit implementer `SEQ_SETTINGS` et `SEQ_TRACK_CONFIG`, soit les retirer temporairement de la surface publique pour eviter les faux-positifs produit.

Fichiers cibles:

- `midi-studio/core/src/ui/OverlayTypes.hpp`
- `midi-studio/core/src/state/CoreState.hpp`
- handlers/rendu associes selon decision.

Commit cible:

- `feat(sequencer): finalize settings/track overlay lifecycle`
  - ou
- `chore(sequencer): remove unused overlay placeholders until implementation`

Definition of done:

- Plus d'overlay declare sans flux d'ouverture/interaction/fermeture.

### Etape B3 - Nettoyage transport scope

But:

- Aligner l'intention et le code (`transport_scope_element_` utilise ou supprime).

Fichiers cibles:

- `midi-studio/core/src/handler/transport/TransportHandler.hpp`
- `midi-studio/core/src/handler/transport/TransportHandler.cpp`

Commit cible:

- `chore(transport): align scope fields with actual bindings`

Definition of done:

- Plus de champ mort / ambigu dans le handler transport.

## Phase C - Fiabilite tests + alignement doc

### Etape C1 - Reparer la baseline des tests natifs oc-note

But:

- Obtenir un retour de compilation lisible, puis remettre `pio test -e native` au vert.

Fichiers cibles:

- `open-control/note/platformio.ini`
- wrappers/toolchain scripts si necessaire
- tests concernes

Commit cible:

- `fix(oc-note): restore native test build diagnostics and pass tests`

Definition of done:

- `test_clock`, `test_engine`, `test_smoke` compilent et passent.

### Etape C2 - Aligner docs memoires avec runtime reel

But:

- Synchroniser defaults et comportement (ou documenter clairement la decision de changer le runtime).

Fichiers cibles:

- `docs/memories/work/feature-ms-sequencer/tech-spec.md`
- `docs/memories/work/feature-ms-sequencer/implementation-plan-v0-framework.md`
- `docs/memories/work/feature-ms-sequencer/README.md`

Commit cible:

- `docs(memories): align sequencer defaults with runtime behavior`

Definition of done:

- Plus de contradiction 1/16 vs 1/8 ni len 18 vs len 8 sans justification explicite.

### Etape C3 - Renforcer CI (optionnel mais recommande)

But:

- Ajouter au moins un gate test automatise sur la couche sequencer.

Commit cible:

- `ci: add native sequencer test job`

## Plan de review finale avant implementation

Avant de coder la Phase A, faire une review finale sur 4 points:

1. **Decision produit defaults**
   - On garde runtime actuel (`len=8`, `1/8`) et on aligne la doc, ou on change runtime pour revenir a `1/16`/`len=18`.
2. **Decision autorite input**
   - Valider l'option recommandee: autorite explicite via provider vue active (pas seulement visibilite LVGL).
3. **Decoupage commits**
   - Valider l'ordre A1 -> A2 -> A3 -> B1 -> B2 -> B3 -> C1 -> C2 (C3 optionnel).
4. **Politique de gate tests**
   - Confirmer que `open-control/note` reste non bloquant jusqu'a C1, puis devient bloquant.

Si ces 4 points sont valides, implementation immediate possible sans autre pre-requis.

## Journal d'avancement

### 2026-02-16 - Etape A1 complete (centralisation mutations step)

Statut: DONE

Commit code:

- `midi-studio/core`: `4afae82` (`refactor(sequencer): centralize step mutation revision flow`)

Fichiers modifies:

- `midi-studio/core/src/state/sequencer/SequencerState.hpp`
- `midi-studio/core/src/handler/sequencer/SequencerMacroPropertyHandler.hpp`
- `midi-studio/core/src/handler/sequencer/SequencerMacroPropertyHandler.cpp`
- `midi-studio/core/src/handler/sequencer/SequencerStepEditHandler.hpp`
- `midi-studio/core/src/handler/sequencer/SequencerStepEditHandler.cpp`

Ce qui a ete fait:

- Ajout d'une API de mutation centralisee dans `SequencerState`:
  - `setStepNoteAt(...)`
  - `setStepVelocityAt(...)`
  - `setStepGateAt(...)`
  - `setStepDataAt(...)`
  - `bumpStepDataRevision()`
- Suppression des increments de revision disperses dans les handlers Macro/StepEdit.
- Le reset sequencer passe maintenant aussi par `bumpStepDataRevision()`.

Notes handover (important pour les devs suivants):

- Les nouvelles APIs valident uniquement `step < MAX_STEPS` (pas `step < length`) pour ne pas changer le comportement historique implicitement.
- Les handlers continuent de verifier `length` avant mutation quand necessaire; ne pas retirer ces gardes sans redefinir explicitement le contrat.
- `closeCancel()` de `SequencerStepEditHandler` restaure maintenant via `setStepDataAt(...)` et ne bump qu'une seule fois.

Gates executes pour cette etape:

- `pio run -e dev` dans `midi-studio/core` -> SUCCESS
- `pio run -e dev` dans `midi-studio/plugin-bitwig` -> SUCCESS
- `pio test -e native` dans `open-control/note` -> ECHEC connu (non bloquant avant C1)

Prochaine etape:

- A2: extraire un utilitaire partage de pagination/index et remplacer les formules dupliquees.

### 2026-02-16 - Etape A2 complete (pagination/index unifies)

Statut: DONE

Commit code:

- `midi-studio/core`: `17ca15e` (`refactor(sequencer): unify page/index resolution helpers`)

Fichiers modifies:

- `midi-studio/core/src/state/sequencer/SequencerState.hpp`
- `midi-studio/core/src/handler/sequencer/SequencerStepHandler.cpp`
- `midi-studio/core/src/handler/sequencer/SequencerMacroPropertyHandler.cpp`
- `midi-studio/core/src/handler/sequencer/SequencerStepEditHandler.cpp`
- `midi-studio/core/src/handler/sequencer/SequencerPatternConfigHandler.cpp`
- `midi-studio/core/src/context/StandaloneContext.cpp`
- `midi-studio/core/src/ui/view/SequencerView.cpp`

Ce qui a ete fait:

- Ajout des helpers centralises de pagination/index dans `SequencerState`:
  - `normalizePage(...)`
  - `pageStartStep(...)`
  - `pageForStep(...)`
  - `resolveStepInPage(...)`
- Remplacement des calculs dupliques handlers/view/context par ces helpers.
- Suppression de la formule repetitive `(len + stepsPerPage - 1) / stepsPerPage` hors `SequencerState`.

Notes handover (important pour les devs suivants):

- `normalizePage(...)` retourne `0` quand `activePageCount()==0`; c'est intentionnel pour eviter tout modulo par zero.
- `resolveStepInPage(...)` valide aussi les bornes pattern (`length`) et `MAX_STEPS`; les callsites n'ont plus besoin de dupliquer ces checks.
- `pageForStep(...)` n'applique pas de clamp; il suppose un `step` deja valide.

Gates executes pour cette etape:

- `pio run -e dev` dans `midi-studio/core` -> SUCCESS
- `pio run -e dev` dans `midi-studio/plugin-bitwig` -> SUCCESS
- `pio test -e native` dans `open-control/note` -> ECHEC connu (non bloquant avant C1)

Prochaine etape:

- A3: normaliser le contrat de mapping encodeur sequencer (suppression des constantes magiques `255/191`).

### 2026-02-16 - Etape A3 complete (contrat mapping encodeur normalise)

Statut: DONE

Commit code:

- `midi-studio/core`: `8f1d13f` (`fix(sequencer): normalize encoder mapping contract`)

Fichiers modifies:

- `midi-studio/core/src/context/StandaloneContext.cpp`
- `midi-studio/core/src/handler/sequencer/SequencerInputUtils.hpp`
- `midi-studio/core/src/handler/sequencer/SequencerStepEditHandler.cpp`

Ce qui a ete fait:

- Suppression des constantes magiques OPT (`255`/`191`) dans le sync sequencer.
- Introduction de helpers partages dans `SequencerInputUtils`:
  - `discreteStepsForProperty(...)`
  - `stepPropertyToNormalized(...)`
- Reutilisation de ces helpers dans le contexte standalone et dans `SequencerStepEditHandler`.

Notes handover (important pour les devs suivants):

- Le contrat de discretisation est maintenant explicite et unique:
  - NOTE = 128 pas
  - VELOCITY = 128 pas
  - GATE = `MAX_GATE_PERCENT + 1`
- Si une future feature change ce contrat, modifier uniquement `SequencerInputUtils` puis verifier les callsites.
- Le helper `stepPropertyToNormalized(...)` centralise aussi le comportement de clamp indirect via `indexToNormalized(...)`.

Gates executes pour cette etape:

- `pio run -e dev` dans `midi-studio/core` -> SUCCESS
- `pio run -e dev` dans `midi-studio/plugin-bitwig` -> SUCCESS
- `pio test -e native` dans `open-control/note` -> ECHEC connu (non bloquant avant C1)

Prochaine etape:

- B1: rendre la regle d'autorite input explicitement lisible dans le code (overlay > vue active > global).

### 2026-02-16 - Etape B1 complete (autorite input explicite)

Statut: DONE

Commits code:

- `open-control/framework`: `fd807b8` (`feat(input): expose active-view provider on overlay manager`)
- `midi-studio/core`: `1b97657` (`feat(input): wire active-view authority in standalone`)
- `midi-studio/plugin-bitwig`: `4611cf0` (`feat(input): wire active-view authority in bitwig context`)

Fichiers modifies:

- `open-control/framework/src/oc/context/OverlayManager.hpp`
- `midi-studio/core/src/context/StandaloneContext.cpp`
- `midi-studio/plugin-bitwig/src/context/BitwigContext.cpp`

Ce qui a ete fait:

- `OverlayManager` expose maintenant `setActiveViewProvider(...)` pour brancher explicitement la couche "vue active" dans `AuthorityResolver`.
- `StandaloneContext` fournit la vue active courante (`MacroView` ou `SequencerView`) comme scope d'autorite.
- `BitwigContext` fournit la vue active via `state_.views.currentViewPtr()` comme scope d'autorite.

Notes handover (important pour les devs suivants):

- Priorite d'autorite rendue explicite dans le code runtime: **overlay > active view > global**.
- Les lambdas provider retournent `0` si la vue n'est pas disponible; le fallback global reste donc possible et explicite.
- L'ordre de cleanup actuel evite l'UAF: les contexts reset `overlay_controller_` avant de detruire les vues.
- Attention cross-repo: `core` et `plugin-bitwig` supposent la presence de `OverlayManager::setActiveViewProvider(...)` cote `open-control/framework`.

Gates executes pour cette etape:

- `pio run -e dev` dans `midi-studio/core` -> SUCCESS
- `pio run -e dev` dans `midi-studio/plugin-bitwig` -> SUCCESS
- `pio test -e native` dans `open-control/note` -> ECHEC connu (non bloquant avant C1)

Prochaine etape:

- B2: finaliser ou fermer proprement `SEQ_SETTINGS` / `SEQ_TRACK_CONFIG` pour supprimer l'ambiguite produit.

### 2026-02-16 - Etape B2 complete (placeholders overlays fermes proprement)

Statut: DONE

Commit code:

- `midi-studio/core`: `cb05586` (`chore(sequencer): remove unused overlay placeholders`)

Fichiers modifies:

- `midi-studio/core/src/ui/OverlayTypes.hpp`
- `midi-studio/core/src/state/sequencer/SequencerState.hpp`
- `midi-studio/core/src/state/CoreState.hpp`
- `midi-studio/core/src/context/StandaloneContext.cpp`

Ce qui a ete fait:

- Suppression de `SEQ_SETTINGS` et `SEQ_TRACK_CONFIG` de l'enum `OverlayType`.
- Suppression des structs/fields state associes non utilises dans `SequencerState`.
- Suppression des enregistrements overlays correspondants dans `CoreState`.
- Nettoyage du reset context pour retirer les appels devenus morts.

Notes handover (important pour les devs suivants):

- Cette etape choisit explicitement l'option "fermer proprement" (pas d'implementation partielle) pour eviter l'ambiguite produit.
- Si on reintroduit ces overlays plus tard, il faudra refaire le flux complet: enum + state + registerItem + rendu + handlers + lifecycle.
- Aucun impact sur les overlays sequencer actifs (`PATTERN_CONFIG`, `STEP_EDIT`, `PROPERTY_SELECTOR`).

Gates executes pour cette etape:

- `pio run -e dev` dans `midi-studio/core` -> SUCCESS
- `pio run -e dev` dans `midi-studio/plugin-bitwig` -> SUCCESS
- `pio test -e native` dans `open-control/note` -> ECHEC connu (non bloquant avant C1)

Prochaine etape:

- B3: aligner le binding transport avec le scope transport declare.

### 2026-02-16 - Etape B3 complete (transport scope aligne)

Statut: DONE

Commit code:

- `midi-studio/core`: `bf72429` (`fix(transport): scope play toggle to transport layer`)

Fichiers modifies:

- `midi-studio/core/src/handler/transport/TransportHandler.hpp`
- `midi-studio/core/src/handler/transport/TransportHandler.cpp`

Ce qui a ete fait:

- Le binding PLAY/STOP (`BOTTOM_CENTER`) est maintenant scope sur `transport_scope_element_` au lieu d'etre global.
- Le commentaire d'interface a ete aligne avec le comportement reel.

Notes handover (important pour les devs suivants):

- Intention et implementation sont maintenant coherentes: controls transport confines au scope transport (main zone), pas bind global brut.
- En cas de changement d'architecture UI transport, verifier que `transport_scope_element_` reste non-null.

Gates executes pour cette etape:

- `pio run -e dev` dans `midi-studio/core` -> SUCCESS
- `pio run -e dev` dans `midi-studio/plugin-bitwig` -> SUCCESS
- `pio test -e native` dans `open-control/note` -> ECHEC connu (non bloquant avant C1)

Prochaine etape:

- Phase C1: restaurer la baseline `open-control/note` native pour rendre les tests bloquants ensuite.
