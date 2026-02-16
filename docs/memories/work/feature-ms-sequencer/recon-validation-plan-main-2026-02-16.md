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
