# Refactor : maintenabilité des produits MIDI Studio

**Scope** : `midi-studio/core`, `midi-studio/plugin-bitwig`, `midi-studio/ui`, frontières avec `device-support` et OpenControl  
**Status** : première intégration et incréments page/device→batch + allègement MIDI Sync intégrés et qualifiés ; suites Java et migrations L6 ouvertes

**Created** : 2026-09-26  
**Updated** : 2026-09-26  
**Nature** : feuille de route d'exécution et passation. Le tableau de la section 5 fait autorité pour l'état courant ; les entrées du journal conservent les preuves historiques.

## 1. Cap et résultat attendu

**Réduire le nombre de responsabilités, de fichiers et de dépendances qu'un développeur doit comprendre pour changer un comportement, tout en conservant les garanties du produit.**

La première livraison doit aligner les limites des tests avec celles du firmware. La deuxième doit protéger les comportements Bitwig aujourd'hui peu testés. Les simplifications architecturales viennent ensuite, sur un parcours Core borné et mesurable.

Le résultat attendu est observable :

- les capacités partagées des builds sont cohérentes et leur dérive est détectée ;
- les mises à jour de paramètres Bitwig disposent de tests comportementaux ;
- le widget `ListOverlay` commun possède une implémentation de référence ;
- le collage d'une page de séquenceur possède un parcours de mutation explicite et couvert ;
- au moins un consommateur de ce parcours utilise des dépendances ciblées plutôt que tout `CoreState` ;
- un groupe de contrôles textuels fragiles est remplacé par des garanties exécutables ;
- l'onboarding indique rapidement où intervenir, sans recopier l'architecture.

Les métriques de lignes et de fichiers servent à localiser les difficultés. Elles ne sont pas des objectifs de suppression.

## 2. Périmètre et autorité de ce document

La revue est approfondie pour Core et ciblée pour Bitwig/UI/device-support. Les lectures dans OpenControl et MS Manager ne constituent pas un audit complet de ces produits. Le loader et la distribution ne sont pas couverts par ces lots. L'audit antérieur de `ms-dev-env` constitue un chantier distinct.

Ce document est une passation de travail dans le dépôt d'orchestration. Les règles d'architecture durables restent dans les dépôts propriétaires ; les décisions transversales/ADRs appartiennent à `petitechose-audio-docs`, conformément à `core/docs/README.md`. Ne pas créer une deuxième référence architecturale ici.

Tous les chemins ci-dessous sont relatifs à la racine de `ms-dev-env`, sauf mention contraire. Chaque sous-produit est un dépôt Git indépendant : les changements et les révisions doivent être suivis par dépôt.

## 3. État de référence et niveau de preuve

### Révisions relevées à la passation

| Dépôt | HEAD |
| --- | --- |
| Core | `e4d8d10ee768331cf3c4e7905034abbd6630ed1c` |
| Plugin Bitwig | `f872b345fd268e1e4d247c8588da4e0eba212096` |
| UI | `f880f20a9eb258a584c11ad93cdfa918ef5bb8f2` |

Les observations portent sur les arbres de travail, pas uniquement sur ces commits. Modifications locales déjà présentes, à préserver et à examiner avant de toucher aux mêmes fichiers :

- Core : `test/device_support_stubs/lvgl.h`, `test/test_DeviceSupportContract/test_main.cpp` ;
- Bitwig : `src/main.cpp` ;
- device-support : `qualification/main.cpp`, `src/ms/device_support/v1/Buffers.hpp`.

Le contrôle de topologie a également signalé des fichiers de build locaux dans `open-control/ui-lvgl/build/alignment/`. La commande `git ls-files build/alignment` n'y a retourné aucun fichier : ne pas les décrire comme des binaires versionnés. Relever à nouveau les statuts avant exécution ; cette liste peut évoluer.

### Vérifications effectuées pendant l'audit

| Vérification | Résultat |
| --- | --- |
| `ms test core` | 206/206 entrées de test, environ 90 secondes |
| `python midi-studio/core/script/dev/check-architecture-contracts.py` | OK |
| `python midi-studio/core/script/dev/check-build-topology.py --workspace-root . --check` | Bloqué par des arbres de travail non propres |
| Build Teensy / qualification matérielle | Non exécutés pendant cette revue |
| Tests Bitwig / Java | Non exécutés pendant cette revue |

Les 206 entrées rapportées par le runner ne représentent pas nécessairement 206 scénarios individuels. Les résultats natifs ne prouvent pas le respect des budgets et latences sur Teensy.

### Constats établis

| ID | Preuve | Conséquence |
| --- | --- | --- |
| F1 | `core/CMakeLists.txt:79` : 256 bindings de boutons ; `core/platformio.ini:49` et `core/sdl/CMakeLists.txt:288` : 272 | Divergence entre limite native et produit ; aucune panne produit démontrée |
| F2 | `core/script/dev/check-architecture-contracts.py` : 5 596 lignes ; `midi_sync_command_contract_errors()` exige notamment `policy::validMode(mode)` et `return applyChoice(0U,` | Certains contrôles figent l'écriture du code plutôt que son résultat |
| F3 | Famille `core/src/state/CoreState*` : 12 fichiers, environ 4 473 lignes ; texte `CoreState&` dans 106 fichiers, tests compris | Dépendances larges ; inventaire textuel, pas graphe sémantique complet |
| F4 | `SequencerHistory.cpp` : 2 575 lignes ; `SequencerStructureEditWorkflow.cpp` : 2 164 ; `SequencerPreparedPageStructureMutationPlan.cpp` : 2 091 | Parcours de mutation à clarifier ; la taille ne prouve pas une duplication |
| F5 | `plugin-bitwig/test/test_NestedIndexUtils/test_main.cpp` est le seul test C++ trouvé ; aucune suite métier Java trouvée dans l'inventaire suivi examiné | Couverture métier locale très limitée par rapport à Core |
| F6 | Deux `src/.../widget/ListOverlay.*`, dans UI et Bitwig, avec contrats et structures très proches | Candidat concret à consolidation, après comparaison des thèmes/API |
| F7 | `core/test/test_SequencerStepHandler/test_main.cpp` : 9 754 lignes | Lisibilité et diagnostic des tests à améliorer par comportements |
| F8 | Docs Core suivies : environ 3 000 lignes ; carte d'architecture et parcours CC Lane actuels | Nettoyage ciblé ; la documentation n'est pas le chantier prioritaire |

Les gains possibles de consolidation sont des hypothèses à vérifier. Aucune suppression de validation transactionnelle ni équivalence complète des deux widgets n'a été démontrée pendant l'audit.

## 4. Garanties à préserver

- **Temps réel** : séparation entre préparation côté boucle principale et consommation ISR ; publication cohérente des snapshots ; ordre et règles de rejet des événements MIDI.
- **Mémoire** : allocations bornées, échecs traités, ownership PSRAM explicite et seuils mémoire existants. Modifier un seuil exige des mesures matérielles et une justification.
- **Mutations** : admission de l'historique et réservation des ressources avant les mutations qui les exigent ; atomicité en cas d'échec ; undo/redo conservé.
- **Persistance** : compatibilité des formats, transactions atomiques, récupération après interruption et cohérence des révisions.
- **UI** : projection de l'état ; transitions métier dans les chemins de commande ; scopes et cycles de vie préservés.
- **Frontières** : hardware partagé dans `device-support`, primitives UI partagées dans `ms-ui`, spécificités Bitwig dans Bitwig.

Prendre comme références `core/docs/CORE_ARCHITECTURE.md`, `ARCHITECTURE_REVIEW_RULES.md` et les contrats proches des API modifiées. Les modules RAII, snapshots, transactions préparées et contrôles mémoire existants sont des acquis à conserver.

## 5. Ordre d'exécution

| Lot | Livraison | Dépendance | État |
| --- | --- | --- | --- |
| L0 | Reprise du contexte et état de référence | Aucune | Effectué |
| L1 | Capacités de build cohérentes | L0 | #178 mergée ; correctif, pins UI/Bitwig et snapshot intégrés ; CI verte |
| L2 | Tests des mises à jour Bitwig | L0 | #28, #30 et #31 mergées ; scénario firmware page/device→batch et suite métier Java qualifiés en local et CI |
| L3 | Consolidation de `ListOverlay` | L2 recommandé avant refactoring Bitwig | UI #15 et Bitwig #29 mergées ; CI UI/Bitwig vertes ; captures avant/après identiques |
| L4 | Parcours pilote de collage de page Core | L1 | #179 mergée ; revue, suite native et CI validées |
| L5 | Dépendances ciblées sur ce parcours | L4 | #180 mergée ; revue, suite native et CI validées |
| L6 | Remplacement d'un groupe de contrôles textuels | L1 ; indépendant de L4/L5 | #181–185 mergées et qualifiées ; persistance/publication, acceptation/fermeture, ClipWorkspace, settlement et consommateurs de sélecteurs couverts ; inspections correspondantes et inventaire >800 lignes retirés |
| L7 | Onboarding et clôture documentaire | Changements concernés stabilisés | Première intégration clôturée : onboarding intégré, validations finales Core 206/206, Bitwig 2/2, UI 2/2, architecture et topologie OK |

Ordre recommandé pour une reprise séquentielle : L0 → L1 → L2 → L3 → L4 → L5 → L6 → L7. Chaque lot doit rester relisible et validable séparément. Ne pas mélanger le déplacement massif de fichiers avec une modification de comportement.

### L0 — Reprendre sans perdre le contexte

1. Lire ce document et les règles locales des dépôts concernés, y compris les éventuels `AGENTS.md` ajoutés depuis l'audit.
2. Relever HEAD et `git status --short` par dépôt ; inspecter les changements existants sur les fichiers du lot.
3. Vérifier les commandes disponibles avec `ms test` et `ms build --help`.
4. Utiliser les résultats ci-dessus si le code est inchangé ; rejouer les contrôles concernés si la base a évolué.
5. Enregistrer le lot choisi et sa révision de départ dans la section de suivi.

**Acceptation** : base de travail identifiée, modifications préexistantes attribuées, premier lot borné. Si le contrôle de topologie exige un arbre propre, utiliser des checkouts dédiés aux révisions voulues ou consigner le blocage ; ne pas nettoyer le travail existant pour le faire passer.

### L1 — Aligner les capacités natives et produit

**Entrées** : `core/CMakeLists.txt`, `core/platformio.ini`, `core/sdl/CMakeLists.txt`, `core/script/dev/check-build-topology.py` et son snapshot.

1. Inventorier les définitions effectives des capacités de boutons, encoders et notifications sur tests natifs, Teensy et SDL/WASM.
2. Confirmer la capacité produit attendue. L'état observé est 272 pour les boutons ; la capacité native de 256 doit être corrigée ou justifiée par un profil de test explicitement distinct.
3. Choisir la solution la plus simple : définition partagée si les outils peuvent la consommer proprement, sinon contrôle automatique d'égalité des valeurs produit. Éviter d'ajouter un générateur uniquement pour trois constantes.
4. Inclure les tests natifs dans la vérification de cohérence, si leur configuration n'est pas déjà couverte. Vérifier que le contrôle échoue réellement sur une divergence volontaire dans une fixture ou copie temporaire.

**Acceptation** : configurations effectives documentées dans le résultat du lot, divergence involontaire supprimée, détection automatique démontrée, tests Core et build Teensy passent. Compiler SDL si sa configuration change ; vérifier WASM si son chemin de configuration est touché. Toute mise à jour de snapshot est examinée, pas simplement régénérée pour obtenir du vert.

### L2 — Protéger le comportement Bitwig avant simplification

**Entrées** :

- `plugin-bitwig/src/handler/host/RemoteControlHostHandler.cpp` ;
- `plugin-bitwig/src/handler/host/PageHostHandler.cpp` ;
- `plugin-bitwig/src/state/ParameterState.hpp` ;
- `plugin-bitwig/host/src/handler/host/DeviceHost.java` ;
- `plugin-bitwig/CMakeLists.txt`, `plugin-bitwig/host/pom.xml`.

Première livraison bornée : **réception firmware des mises à jour de paramètres**, avec le minimum de doublures pour protocole/encoders et les classes métier réelles.

Scénarios à couvrir après lecture des règles existantes :

1. Une mise à jour valide affecte le slot attendu et laisse les autres inchangés.
2. Un index invalide n'écrit dans aucun slot.
3. Un batch partiel respecte ses masques et maintient la cohérence entre valeur, modulation et affichage.
4. Un changement de page/device suivi d'un batch produit l'état prévu par le contrat de synchronisation.

Pour le quatrième scénario, établir d'abord les règles de séquence/réinitialisation réellement implémentées. Si le comportement attendu est ambigu, consigner la décision à obtenir avant d'en faire une assertion. Un test de caractérisation ne doit pas transformer silencieusement un bug en contrat.

Examiner ensuite le batching Java : isoler sa logique testable seulement si cela est nécessaire et local. Ajouter une sous-livraison Java dédiée, avec commande et wiring Maven/CI explicites, plutôt que modifier simultanément le protocole et les deux consommateurs.

**Acceptation première livraison** : nouveaux scénarios exécutés par `ms test plugin-bitwig`, échecs lisibles, pas de dépendance à une instance Bitwig pour ces tests. Le bilan précise séparément ce qui reste à vérifier en Java et en intégration réelle. Les scénarios sélectionneurs/reconnexion constituent la suite du backlog, pas une extension automatique de ce lot.

### L3 — Donner une implémentation de référence à `ListOverlay`

**Entrées** : `ui/src/ms/ui/widget/ListOverlay.*`, `plugin-bitwig/src/ui/widget/ListOverlay.*`, leurs consommateurs et inventaires CMake/PlatformIO.

1. Comparer les comportements : liste vide, remplacement, ajout incrémental, sélection hors bornes, défilement, affichage/masquage et destruction.
2. Relever les différences de thème. L'implémentation Bitwig dépend de `plugin-bitwig/src/ui/theme/BitwigTheme.hpp` : l'équivalence visuelle n'est pas acquise.
3. Compléter uniquement les variations nécessaires dans le widget partagé ; conserver le thème produit au niveau du consommateur.
4. Migrer les consommateurs Bitwig. Une adaptation locale de style reste possible ; une seconde implémentation du cycle de vie de la liste ne doit pas subsister sans justification.
5. Supprimer les sources devenues inutiles des inventaires de build après recherche des références.

**Acceptation** : un seul moteur de liste pour les consommateurs migrés, API publique limitée aux besoins observés, tests des cas limites touchés et builds des deux produits passent. Vérifier visuellement les sélecteurs concernés en simulation et comparer aux captures avant migration.

**Attention test** : lacune initiale corrigée localement après revue : le CMake autonome de `ui` déclare aussi `test_VirtualListOverlay` (voir journal des correctifs et README UI). Son exécution automatique en CI reste à raccorder.

### L4 — Simplifier un parcours Core : collage d'une page de séquenceur

**Entrées** :

- `core/src/handler/sequencer/SequencerStructureEditWorkflow.cpp` ;
- `SequencerPreparedPageStructureMutationPlan.*` et `SequencerPreparedPageStructureTransaction.*` dans le même dossier ;
- `core/src/state/sequencer/SequencerHistory.*` ;
- `core/src/state/CoreStateSequencerHistoryRecording.cpp` ;
- `core/test/test_SequencerPreparedPageStructureMutationPlan/test_main.cpp` ;
- `core/test/test_SequencerHistoryPreparedTransactions/test_main.cpp`.

1. Tracer un collage de page depuis la commande jusqu'à la publication. Identifier les branches réellement empruntées, les données figées et les propriétaires des ressources.
2. Produire une table courte « étape → fonction → invariant → test » dans le résultat du lot : validation, préparation/réservation, admission historique, mutation, publication.
3. Choisir **une** simplification démontrée : validation strictement redondante, coordination au mauvais niveau ou frontière difficile à lire. Si rien n'est redondant, améliorer l'API/ownership au point précis qui gêne la lecture ; ne pas inventer une suppression.
4. Conserver ou compléter les tests : collage valide, no-op/rejet, capacité insuffisante, échec d'allocation, refus d'historique, undo/redo. Pour chaque échec avant commit, vérifier l'absence de mutation partielle.
5. Ne sortir du périmètre page que si une dépendance directe l'impose ; conserver cette justification dans la revue.

**Acceptation** : parcours avant/après identifiable, une réduction de coordination ou de dépendances démontrée, invariants couverts, suite Core et architecture passent, build Teensy et budgets passent. Mesures matérielles nécessaires si le travail modifie allocation, placement mémoire ou chemin temps réel.

### L5 — Réduire une dépendance large à `CoreState`

**Entrées** : `core/src/state/CoreState.hpp`, consommateurs du parcours L4, `core/src/handler/sequencer/SequencerHistoryDomainServices.hpp`. Exemple existant de dépendances ciblées : `core/src/sequencer/SequencerRuntimeService.*`.

1. Sur le parcours pilote, inventorier les membres de `CoreState` réellement utilisés par un consommateur.
2. Remplacer sa dépendance globale par les références de domaines/opérations nécessaires, en réutilisant les frontières existantes.
3. Garder l'assemblage au niveau composition ; simplifier la fixture du consommateur si elle n'a plus besoin du produit complet.
4. Vérifier les appels et durées de vie. Ne pas remplacer `CoreState&` par une structure qui réexpose tout l'agrégat sous un autre nom.

**Acceptation** : au moins un consommateur de production n'accède plus à l'agrégat complet ; sa dépendance effective est plus étroite ; comportement inchangé et tests pertinents passent. Donner le décompte et les fichiers avant/après. Étendre à d'autres consommateurs seulement après revue du pilote.

### L6 — Remplacer un contrôle textuel fragile par des tests de contrat

**Entrée pilote** : `midi_sync_command_contract_errors()` dans `core/script/dev/check-architecture-contracts.py`, ainsi que `DeviceSettingsDomainServices::applyMidiSyncMode()` et `applyChoice()` ; retrouver leurs fichiers via recherche de symboles.

1. Lister chaque garantie actuellement cherchée textuellement et repérer ses tests exécutables éventuels.
2. Couvrir les garanties métier, notamment validation du mode et publication après persistance réussie ; injecter un échec de persistance pour vérifier l'absence de publication interdite.
3. Montrer que ces tests détectent une violation représentative, dans une copie temporaire ou par injection prévue par le test.
4. Retirer uniquement les recherches textuelles dont la garantie est effectivement remplacée. Conserver les règles de dépendance et de placement mémoire utiles.

**Acceptation** : chaque règle retirée possède une preuve de remplacement, les tests échouent sur la violation et passent sur le code correct ; un renommage/local refactoring équivalent n'est plus rejeté à cause de ces marqueurs. Les autres contrôles d'architecture continuent de passer.

Une séparation ultérieure du script par famille de règles peut suivre ; elle ne remplace pas ce travail de fond.

### L7 — Rendre la reprise documentaire courte et fiable

**Entrées** : `core/docs/README.md`, `DEVELOPER_ONBOARDING.md`, `CORE_ARCHITECTURE.md`, `CC_LANE_FEATURE.md`, `ARCHITECTURE_REVIEW_RULES.md`, ainsi que les pointeurs Core dans les docs de `ms-dev-env`.

1. Proposer un parcours initial court : exécuter les tests → lire la carte d'architecture → suivre une fonctionnalité → consulter les règles pertinentes.
2. Mettre à jour les pointeurs affectés par les lots ; remplacer les anciennes références absentes plutôt que recréer les documents obsolètes.
3. Garder une seule définition de chaque règle, puis faire des liens. Conserver les explications d'invariants utiles à proximité des API.
4. Traiter `core/docs/LOCAL_REFACTOR_ROADMAP.md` comme note locale historique non suivie : aucune suppression du travail local au titre du nettoyage des docs publiées.

**Acceptation** : liens locaux concernés valides, commandes vérifiées, aucun parcours d'entrée contradictoire, décisions durables reportées dans leur dépôt propriétaire. Cette feuille de route reste un suivi temporaire ; à clôture, conserver les décisions utiles puis retirer le plan de la documentation active en s'appuyant sur l'historique Git.

## 6. Validation pratique

Depuis la racine du workspace, avec le runtime de développement activé :

```powershell
ms test
ms test core
ms test plugin-bitwig
python midi-studio/core/script/dev/check-architecture-contracts.py
ms build core --target teensy --env dev
python midi-studio/core/script/dev/check-build-topology.py --workspace-root . --check
```

Dans l'environnement Windows de l'audit, les exécutables utilisés sont `.venv/Scripts/ms.exe` et `.venv/Scripts/python.exe`. `ms test` seul liste les cibles ; ce n'est pas l'exécution de toute la suite.

Pour itérer sur un test CMake ciblé :

```powershell
ms test core --test SequencerPreparedPageStructureMutationPlan
```

`--test` accepte le nom avec ou sans préfixe `test_`. Le preset `core/CMakePresets.json` propose aussi `native-sanitized` et `native-fuzz` ; utiliser les tests instrumentés adaptés si les codecs ou frontières mémoire changent, avec une toolchain compatible.

Les commandes exactes SDL/WASM, firmware Bitwig et Maven/CI doivent être prises dans la configuration courante des dépôts et consignées lors du lot concerné. Elles n'ont pas été exécutées pendant cet audit : ne pas présenter une commande supposée comme une validation acquise.

Pour un changement touchant les headers partagés ou la composition firmware, suivre également les contrôles downstream exigés par `core/docs/ARCHITECTURE_REVIEW_RULES.md`. Le script existant `core/script/dev/check-downstream-compat.ps1` appelle `pio run -e dev` dans Bitwig ; il exige le bon runtime PlatformIO.

## 7. Suivi, revue et définition de terminé

À chaque livraison, ajouter ici une entrée courte, avec lien vers la PR ou le commit si disponible :

```text
Lot / état :
Dépôts et révisions de départ :
Constat traité :
Changement livré :
Preuve du gain de maintenabilité :
Commandes exécutées et résultats :
Vérifications non exécutées / blocages :
Décision durable et emplacement :
Prochain lot :
```

Un lot est terminé lorsque son critère d'acceptation est satisfait, ses vérifications pertinentes sont exécutées et les limites restantes sont explicites. Une qualification matérielle requise mais indisponible laisse cette partie bloquée, même si les tests natifs passent.

La priorité initiale était L0 puis la divergence 256/272 de L1. Pour la reprise actuelle, utiliser le tableau de la section 5 et la dernière entrée du journal.

### Suivi des livraisons

#### L0 — Reprise du contexte et état de référence

- Lot / état : terminé le 2026-09-26 ; aucun changement de code.
- Dépôts et révisions de départ : Core `e4d8d10e` (`main` ; `test/device_support_stubs/lvgl.h` et `test/test_DeviceSupportContract/test_main.cpp` modifiés localement) ; Plugin Bitwig `f872b345` (`codex/bitwig-boot-diagnosis` ; `src/main.cpp` modifié) ; UI `f880f20a` (propre) ; device-support `20c32843` (`codex/lvgl-buffer-alignment` ; `qualification/main.cpp` et `src/ms/device_support/v1/Buffers.hpp` modifiés) ; open-control/ui-lvgl `4d627697` (`codex/lvgl-buffer-alignment` ; `Bridge.*` et tests modifiés, `build/` non suivi) ; ms-manager `f94bf213` (propre).
- Constat traité : contexte repris sans nettoyer le travail existant ; aucun `AGENTS.md` dans les sous-dépôts ; aucun fichier des lots L1+ modifié localement.
- Changement livré : aucun.
- Preuve du gain de maintenabilité : les modifications locales sont rattachées au chantier alignement LVGL (Core/device-support/ui-lvgl) et au diagnostic boot Bitwig ; le premier lot peut être borné sans y toucher.
- Commandes exécutées et résultats : `git status --short` et `git rev-parse HEAD` par dépôt ; `ms test` (catalogue) ; `ms test --help`, `ms build --help`.
- Vérifications non exécutées / blocages : contrôle de topologie bloqué dans le workspace principal par les arbres non propres préexistants (contourné en L1 par un bench dédié).
- Note d'attribution : pendant la session, le dépôt `ms-dev-env` a reçu des modifications `ms/...` et une feuille de route `refactor-ms-dev-env-maintainability.md` issues d'un chantier parallèle ; elles n'ont pas été touchées par L0/L1.
- Décision durable et emplacement : sans objet pour ce lot.
- Prochain lot : L1.

#### L1 — Capacités de build cohérentes

- Lot / état : terminé localement le 2026-09-26 ; branche Core `codex/core-maintainability-l1` (worktree `.worktrees/core-maintainability-l1`), commits `0d306072` et `58aa10a2`, non poussés.
- Dépôts et révisions de départ : Core `e4d8d10e` ; bench de contrôle `.tmp/l1-topology-20260926` avec Bitwig `f872b345`, device-support `20c32843`, UI `f880f20a`, ui-lvgl `4d627697`.
- Constat traité : F1 — tests natifs bornés à 256 contre 272 côté produit. L'inventaire a aussi révélé que `OC_MAX_BUTTONS` valait 64 (défaut framework) en SDL/WASM contre 48 en natif/PlatformIO.
- Changement livré : `core/CMakeLists.txt` → `OC_MAX_BUTTON_BINDINGS=272` ; `core/sdl/CMakeLists.txt` → `OC_MAX_BUTTONS=48` pour l'app Core uniquement (le build SDL partagé sert aussi Bitwig, laissé à sa configuration) ; `check-build-topology.py` lit désormais les définitions réelles de `oc_framework_native` et refuse toute divergence des quatre capacités entre les profils `coreNativeCmake`, `corePioNative`, `coreTeensy`, `sdlWasm` ; snapshot régénéré et examiné.
- Configurations effectives après alignement (pending/buttons/buttonBindings/encoderBindings) : natif CMake, `env:native` PlatformIO, Teensy et SDL/WASM = 96/48/272/96. Le firmware Bitwig reste à 64/64/64/32 (profil produit distinct, hors règle d'égalité).
- Preuve du gain de maintenabilité : le profil `coreNativeCmake` du snapshot reflète enfin la réalité (48/272/96/96 au lieu de 64/64/32/96) ; un retour volontaire à 256 fait échouer le contrôle avec `buttonBindings: coreNativeCmake=256, corePioNative=272, coreTeensy=272, sdlWasm=272`.
- Commandes exécutées et résultats : `--self-test` OK (13 contrats) ; `--write-snapshot` puis `--check` PASS dans le bench clean ; divergence volontaire → FAIL ciblé → `reset --hard` → PASS ; suite native Core 206/206 en 60,6 s (dépendances propres) ; `check-architecture-contracts.py` OK ; SDL natif compilé (`midi_studio_core.exe` lié) ; WASM compilé (`midi_studio_core.html` lié) ; Teensy `ms build core --target teensy --env dev` BUILD OK (FLASH 18 %, RAM1 70 %, RAM2 35 %, PSRAM 14 %, 110 s).
- Vérifications non exécutées / blocages : qualification matérielle non exécutée ; tests Bitwig non lancés (lot L2) ; `check-downstream-compat.ps1` non requis (aucun header exporté ni fichier déplacé) ; premier build natif du worktree bloqué par le chantier aligment LVGL local non commité, résolu en épinglant le checkout device-support propre `20c32843`.
- Décision durable et emplacement : la règle d'égalité vit dans `check-build-topology.py`, déjà exécutée par la CI Core (`.github/workflows/ci.yml`) ; aucune constante partagée ni générateur ajoutés (trois valeurs, coût non justifié).
- Prochain lot : L2 (tests comportementaux Bitwig) ; L3 recommandé avant tout refactoring Bitwig.

#### L2 — Protéger le comportement Bitwig avant simplification (première livraison)

- Lot / état : première livraison terminée localement le 2026-09-26 ; branche Bitwig `codex/bitwig-maintainability-l2` (worktree `.worktrees/bitwig-maintainability-l2`), commit `a9f1f86`, non poussée.
- Dépôts et révisions de départ : Bitwig `f872b345`.
- Constat traité : F5 — seule `NestedIndexUtils` était couverte. Livraison bornée à la réception des mises à jour de paramètres ; le batching Java reste une sous-livraison dédiée.
- Changement livré : `RemoteControlHostHandler` applique les messages à `ParameterState` via un port `ParameterEncoderPort` (adaptateur `EncoderApiParameterPort` en production) et `Protocol::ProtocolCallbacks` ; capacités paramètres isolées dans `state/ParameterCapacity.hpp` (re-exportées par `Constants.hpp`) ; constructeur/destructeur de `BitwigContext` déplacés dans le `.cpp` ; tests `test_RemoteControlParameterUpdates` (5 cas) et wiring CMake via `MS_PLUGIN_BITWIG_FRAMEWORK_TESTS` (Sources framework `Signal.cpp` / `NotificationQueue.cpp`).
- Preuve du gain de maintenabilité : les règles de réception s'exécutent sans instance Bitwig ni graphe d'entrée OpenControl ; une inversion volontaire du skip écho KNOB produit `[FAIL] KNOB echoes must keep the optimistic value` ; le comportement « offset de modulation calculé avant l'application des valeurs dirty du batch » est épinglé et signalé comme décision produit à confirmer.
- Commandes exécutées et résultats : CMake/CTest direct sur le worktree (invocation `ms test plugin-bitwig` vérifiée en dry-run) → `test_NestedIndexUtils` + `test_RemoteControlParameterUpdates`, 2/2 PASS ; échec de mutation ciblé puis revert ; compilation SDL Bitwig avec les sources du worktree → `midi_studio_bitwig.exe` lié.
- Vérifications non exécutées / blocages : scénario 4 « changement de page/device puis batch » non couvert — les règles implémentées sont établies (DeviceChangeHeader passe tous les slots en loading et réinitialise le sélecteur de pages ; DevicePageChange remplit les slots et sort du loading ; le batch n'applique que les masques dirty) mais leur test demande la même extraction page/device ; sous-livraison Java (JUnit/surefire + wiring Maven/CI) à cadrer ; intégration réelle Bitwig non testée.
- Décision durable et emplacement : le port encodeur et la découpe des capacités restent locaux à Bitwig ; aucun changement de protocole. Le snapshot de topologie Core suit `bitwig/CMakeLists.txt` : à régénérer lorsque la révision Bitwig sera épinglée.
- Prochain lot : L3 (ListOverlay) ; la suite L2 (scénario 4 + Java) reste ouverte.

#### L3 — ListOverlay : une implémentation de référence

- Lot / état : migration terminée localement le 2026-09-26 ; branche UI `codex/ui-maintainability-l3` (commit `411c8ad`) et branche Bitwig `codex/bitwig-maintainability-l3` (commit `b188c7a`, empilée sur L2 `a9f1f86`), non poussées.
- Dépôts et révisions de départ : UI `f880f20a`, Bitwig `a9f1f86`.
- Constat traité : F6 — deux implémentations quasi identiques. Différences inventoriées : namespace, trois alias d'opacité (`OVERLAY_BG=OPA_90`, `SCROLLBAR=OPA_30`, `HIDDEN=OPA_TRANSP`), overload `setItems(const char* const*, size_t)` seulement côté UI, annotations `FLASHMEM` côté UI, déclaration morte `appendItemsIfPossible` (jamais définie) des deux côtés.
- Changement livré : BaseSelector Bitwig consomme `ms::ui::ListOverlay` ; `plugin-bitwig/src/ui/widget/ListOverlay.*` supprimés et retirés de `MidiStudioBitwigSources.cmake` (−433 lignes nettes) ; déclaration morte retirée du widget partagé. Aucune variation produit n'a été nécessaire : le widget partagé n'utilise que `base_theme` et `CoreFonts`.
- Preuve du gain de maintenabilité : un seul moteur de liste pour les deux produits ; l'équivalence des constantes de thème est démontrée par les alias ; l'API partagée est un sur-ensemble des besoins observés (le seul consommateur Bitwig, `BaseSelector`/`ViewSelector`, n'utilise que les setters, la sélection, l'affichage et les accesseurs).
- Commandes exécutées et résultats : SDL Bitwig reconstruit avec les sources L3 + UI partagé → `midi_studio_bitwig.exe` lié ; SDL Core reconstruit avec le même UI partagé → `midi_studio_core.exe` lié ; tests Bitwig validés au commit parent `a9f1f86` (le lot ne touche aucun fichier testé).
- Vérifications non exécutées / blocages : vérification visuelle en simulation et captures non réalisées (à faire avant merge) ; build firmware Bitwig non exécuté — le widget partagé est annoté `FLASHMEM`, donc le placement du code Bitwig passe en flash (Core le fait déjà, mais le contrôle downstream reste à faire) ; `ui/test/test_VirtualListOverlay/test_main.cpp` n'est exécuté par aucun runner : `ui/CMakeLists.txt` ne déclare que `test_CurvePreviewGeometry`, le dépôt UI n'a pas de workflow CI, `ms test` n'a pas de cible UI et le superbuild Core ne compile pas les tests UI. Les dossiers `test_CurvePreviewBand/` et `test_CurvePreviewWidget/` sont vides localement (artefacts, pas de sources suivies). Raccordement proposé : construire une cible de tests UI (sources ms-ui + LVGL + `lv_conf` de test), puis l'exécuter soit depuis la CI Core, soit via une cible `midi-studio-ui` ajoutée au catalogue `ms test` (outillage `ms/` actuellement en refactor parallèle).
- Décision durable et emplacement : `ms-ui` reste propriétaire du widget ; toute variation visuelle produit reste au niveau du consommateur (aucune nécessaire ici).
- Prochain lot : L4.

#### L4 — Parcours pilote : collage de page

- Lot / état : terminé localement le 2026-09-26 ; branche Core `codex/core-maintainability-l4` (worktree `.worktrees/core-maintainability-l4`, empilée sur L1 `58aa10a2`), commit `fadb19ff`, non poussée.
- Dépôts et révisions de départ : Core `58aa10a2`.
- Parcours tracé (commande → publication) : `pasteStructureSelection` / `pasteCurrentStructure` / `pasteStepClipboardAt` → `Transaction::openBoundary` (rejet du Step Content Draft actif, commit du boundary Pattern) → builder de préflight `buildSequencer…PasteMutationPlan` → `begin` (admission historique + `preparedPatternEditReady`) → `revalidateMutationPlan` → `mutatePlan` (`executeMapped`/`executeDelete`) → `sealAndCommit` (scellement puis commit unique) → `finalizeCommittedPlan` + settle appelant (pageHold, preview). Table étape → fonction → invariant → test fournie dans le rapport de lot ; les tests existants couvrent rejet, no-op sémantique, capacité insuffisante, rollback pré-commit, refus d'historique, undo/redo et publication post-commit.
- Constat traité : aucune validation ni coordination strictement redondante démontrée (chaque étage a un rôle distinct ; la revérification est une ré-analyse, pas une copie). La frontière illisible était le « settlement » : un `uint16_t` packé (`outcome << 8 | focus`) échangé entre trois helpers quasi identiques et leurs appelants, avec la double table préflight/résultat dupliquée trois fois.
- Changement livré : type nommé `PreparedStructureSettlement` (2 octets, ABI de retour identique) ; fabriques Failed/NoChange/Committed ; helper unique `applyPreparedPageStructurePlan`, propriétaire de la règle « un préflight non-Ready n'exécute jamais le plan, NoChange porte le focus, seul StepPaste conserve le focus commité pour le curseur » ; trois helpers de collage simplifiés.
- Preuve du gain de maintenabilité : les trois doubles switchs (~28 lignes chacun) deviennent trois délégations de ~6 lignes ; 24 packs et 15 unpacks supprimés ; aucune sémantique modifiée (206/206).
- Commandes et résultats rapportés (syntaxe `--workspace` corrigée lors de la revue) : `ms --workspace .tmp/l4-runner-bench test core` → **206/206 (172,6 s)** ; `check-architecture-contracts.py` OK ; `ms --workspace .tmp/l4-runner-bench build core --target teensy --env dev` → **BUILD OK** 50 s (FLASH 18 %, RAM1 70 %, RAM2 35 %, PSRAM 14 %) ; `ms --workspace .tmp/l4-runner-bench test plugin-bitwig` → 2/2 OK (branche L3).
- Incident significatif (preuve F2 pour L6) : la première exécution a fait échouer `check-architecture-contracts.py`, car une règle exige la présence textuelle de `executeSequencerPreparedPageStructureMutationPlan` dans chaque helper ; le refactor déplaçait — correctement — l'appel dans le helper partagé. La règle a été reciblée sur la garantie structurelle (délégation exigée + exécution unique dans le helper). C'est exactement le risque décrit par l'audit : un refactoring correct rejeté à cause de son écriture.
- Vérifications non exécutées / blocages : qualification matérielle non exécutée ; la règle reste textuelle (cible L6) ; le bench runner (`--workspace`) est la méthode recommandée pour rejouer les suites sur une branche sans toucher au checkout principal.
- Prochain lot : L5.

### Séquence d'atterrissage (2026-09-26)

Branches poussées et PR ouvertes :

| Lot | Dépôt | Branche | PR | Base |
|---|---|---|---|---|
| L1 | Core | `codex/core-maintainability-l1` | [#178](https://github.com/petitechose-midi-studio/core/pull/178) | `main` |
| L4 | Core | `codex/core-maintainability-l4` | [#179](https://github.com/petitechose-midi-studio/core/pull/179) | `codex/core-maintainability-l1` |
| L5 | Core | `codex/core-maintainability-l5` | [#180](https://github.com/petitechose-midi-studio/core/pull/180) | `codex/core-maintainability-l4` |
| L6 | Core | `codex/core-maintainability-l6` | [#181](https://github.com/petitechose-midi-studio/core/pull/181) | `codex/core-maintainability-l5` |
| L2 | Plugin Bitwig | `codex/bitwig-maintainability-l2` | [#28](https://github.com/petitechose-midi-studio/plugin-bitwig/pull/28) | `main` |
| L3 | Plugin Bitwig | `codex/bitwig-maintainability-l3` | [#29](https://github.com/petitechose-midi-studio/plugin-bitwig/pull/29) | `codex/bitwig-maintainability-l2` |
| L3 | UI | `codex/ui-maintainability-l3` | [#15](https://github.com/petitechose-midi-studio/ui/pull/15) | `main` |

Ordre de merge : **UI #15 → Bitwig #28 → Bitwig #29 → Core #178 → Core #179 → Core #180 → Core #181**. Intégrer d'abord les correctifs locaux sur leurs branches, puis mettre à jour les bases des PR empilées. Les statuts distants ci-dessus sont ceux rapportés précédemment, non revérifiés pendant cette correction.

Après merge :

1. Avancer les pins de qualification Core (`MIDI_STUDIO_BITWIG_SHA` et `MIDI_STUDIO_UI_SHA` dans `.github/workflows/ci.yml`, plus `ms-ui` dans `platformio.ini`) vers les révisions mergées. `.ms/repos.lock.json` est un inventaire local de synchronisation, pas le pin produit ; ne pas y déclarer des HEAD que les checkouts principaux n'ont pas réellement adoptés.
2. Régénérer le snapshot de topologie Core (les hashes des CMake UI/Bitwig sont suivis) dans un bench propre aux dépendances exactes, puis commiter le snapshot. Les hashes Git des fichiers d'entrée portent sur leur version commitée : commiter les pins avant cette génération.
3. Rejouer `ms test core` et `ms test plugin-bitwig` sur les `main` mergés.
4. Rejouer CTest UI sur les révisions intégrées. La qualification visuelle des sélecteurs et ses captures restent exigées **avant merge de L3** ; les tests headless ne s'y substituent pas.

Points de revue à ne pas perdre : L2 — l'offset de modulation du batch utilise la valeur pré-batch (décision produit à confirmer, épinglée par test) ; L3 — captures et exécution CI des tests UI restantes. Le succès firmware #29 a été rapporté précédemment (58 s), non rejoué ici ; L1 — intégrer le correctif SDL puis régénérer le snapshot à la fenêtre de coordination (changements UI et Bitwig inclus) ; L4 — règle d'architecture reciblée sur la délégation.

### L6 — Règles textuelles remplacées par des garanties exécutables (première livraison)

- Lot / état : terminé localement le 2026-09-26 ; branche Core `codex/core-maintainability-l6` (worktree `.worktrees/core-maintainability-l6`, empilée sur L5 `e43c001d`), commit `97f61835`, PR [#181](https://github.com/petitechose-midi-studio/core/pull/181).
- Constat traité : `midi_sync_command_contract_errors()` figeait la forme du header (`ApplyStatus`, `ApplyResult`, signatures), le corps de `applyMidiSyncMode` (`policy::validMode`, délégation `applyChoice(0U,`), l'ordre reconcile → no-change → stage → commit → publish et le nombre de retours `PERSISTENCE_FAILED` (== 3).
- Changement livré : ces contrôles sont retirés du script ; `test_DeviceSettingsDomainServices` est documenté comme le remplacement exécutable (validation du mode, no-change sans écriture, persistance avant publication, échecs structurés `IO_ERROR` / `COMMIT_FAILED` sans publication, absence de publication périmée après échec). Les règles de cycle de vie du sélecteur partagé restent textuelles (pas encore de remplacement exécutable).
- Preuves : un refactor local équivalent (constante `midiSyncModeRow`) est rejeté par l'ancienne règle puis accepté après retrait ; désactiver le garde `validMode` fait échouer la suite (`Assertion failed: !invalid.success()`) puis revert ; `check-architecture-contracts.py` OK ; `ms test core` **206/206** (aucun changement firmware, Teensy non requis).
- Décision durable : chaque retrait futur suit le même patron — garantir d'abord par test exécutable, puis retirer le marqueur textuel ; les règles de dépendance et de placement mémoire restent.
- Familles restantes connues (incréments ultérieurs) : les règles textuelles reciblées pendant L4/L5 (settlement, view switcher, clip workspace) et les contrôles de cycle de vie des sélecteurs.
- Prochain lot : L7, puis incréments L6 au fil des refactors.

**Prochaine action : terminer les merges protégés de la pile Core, puis rejouer les validations sur les révisions intégrées. Les pins UI/Bitwig et le snapshot sont coordonnés.**

### L5 — dépendances ciblées (première livraison)

- Lot / état : terminé localement le 2026-09-26 ; branche Core `codex/core-maintainability-l5` (worktree `.worktrees/core-maintainability-l5`, empilée sur L4 `fadb19ff`), commits `6191aad4` (view switcher) et `e43c001d` (clip workspace), PR [#180](https://github.com/petitechose-midi-studio/core/pull/180).
- Constat : sur le parcours L4, aucun consommateur n'utilise `CoreState&` (workflow, transaction et `SequencerStepHandler` déjà ciblés). Premier consommateur large retenu : `ViewSwitcherHandler`, qui n'utilisait que six tranches d'état et quatre opérations d'historique de projet.
- Changement livré : `ViewSwitcherHandler::Refs` remplace `CoreState&` — six références ciblées plus `Refs::HistoryOps` (quatre pointeurs de fonction + contexte, même idiome que les adaptateurs de transaction) ; le `.cpp` du handler n'inclut plus `state/CoreState.hpp` ; `StandaloneGlobalHandlerAssembly` possède les thunks ; `CoreState` reste inchangé ; `test_ViewSwitcherHandler` recâblé sur les mêmes `Refs`.
- Preuve du gain : le handler ne peut plus atteindre l'agrégat ; sa dépendance est énumérable (six tranches, quatre opérations) ; l'inclusion de `CoreState.hpp` disparaît de son unité de compilation.
- Commandes et résultats rapportés (syntaxe `--workspace` corrigée lors de la revue) : `ms --workspace .tmp/l4-runner-bench test core` → **206/206** (126,6 s, `test_ViewSwitcherHandler` inclus) ; `ms --workspace .tmp/l4-runner-bench build core --target teensy --env dev` → BUILD OK 61 s, budgets inchangés (FLASH 18 %, RAM1 70 %, RAM2 35 %, PSRAM 14 %) ; contrats d'architecture OK.
- Vérifications non exécutées / blocages : qualification matérielle ; la règle d'architecture de ce handler reste du même ordre textuel (cible L6).
- Deuxième consommateur livré (`e43c001d`) : `ClipWorkspaceHandler::Refs` — quinze tranches d'état plus `ClipWorkspaceOps` (douze thunks : création, bascule d'édition, suppression, duplication, déplacement, stop slot, comportements clip/scène, demandes de lancement/stop/scène, état des pistes partagées) ; le `.hpp` et le `.cpp` n'incluent plus `state/CoreState.hpp` ; assemblage dans `SequencerFeatureModule` et recâblage du harnais `test_SequencerStepHandler`. Quatre règles d'architecture qui figeaient le texte des appels `core_.…` ont été reciblées (troisième cas d'école pour L6).
- Suite L5 (optionnelle) : les méthodes statiques des services de presets (`SequencerChordPresetDomainServices`, `SequencerPatternPresetDomainServices`, `SequencerStepPresetDomainServices`) restent des consommateurs ponctuels de `CoreState&` par appel ; aucune urgence.
- Prochain lot : L6.

### Correctifs après revue indépendante — 2026-09-26

**Livraison locale, non commitée/non poussée.** Trois worktrees concernés :

| Branche | Fichiers / correction | Validation indépendante |
| --- | --- | --- |
| `.worktrees/core-maintainability-l6` | `test/test_DeviceSettingsDomainServices/test_main.cpp` : le stockage observe l'ancien mode pendant `write()` et `commit()` ; compte les deux opérations et vérifie leur absence pour un no-op sur stockage propre | Core **206/206**, 41,16 s ; mutation publication avant commit avec rollback désormais rejetée ; mutation validation désactivée également rejetée ; architecture OK |
| `.worktrees/core-maintainability-l1` | `script/dev/check-build-topology.py` : capacités littérales sur la cible SDL attendue, seulement hors condition ou sous `APP_ID STREQUAL "core"` ; rejet des autres scopes, valeurs indirectes, doublons et définitions non reconnues | Self-test **14 contrats**, dont six configurations négatives ; remplacement réel du bloc Core par `if(FALSE)` rejeté ; inventaire du bench L1 identique au snapshot |
| `.worktrees/ui-maintainability-l3` | `CMakeLists.txt`, `cmake/MidiStudioUiLvglTests.cmake`, test LVGL et README : cible headless CTest, dépendances explicites, assertions actives ; scénario du widget partagé ajouté | Build Zig Debug ; CTest **2/2**, 0,51 s, contre le checkout ui-lvgl propre du bench L1 |

Les quatre espaces de fin de ligne de `ClipWorkspaceHandler.cpp` ont aussi été retirés dans L6. Le correctif L1 est porté uniquement par sa branche propriétaire : le propager lors de la mise à jour de la pile L4/L5/L6, avant validation finale intégrée. Aucun comportement de production n'a été modifié par ces correctifs.

Commandes de reprise depuis la racine du workspace (outils locaux sous Windows) :

```powershell
.venv/Scripts/ms.exe --workspace .tmp/l4-runner-bench test core
.venv/Scripts/python.exe .worktrees/core-maintainability-l6/script/dev/check-architecture-contracts.py
.venv/Scripts/python.exe .worktrees/core-maintainability-l1/script/dev/check-build-topology.py --self-test
tools/cmake/bin/cmake.exe -S .worktrees/ui-maintainability-l3 -B .tmp/l3-ui-review -G Ninja -DCMAKE_BUILD_TYPE=Debug -DCMAKE_MAKE_PROGRAM="$PWD/tools/ninja/ninja.exe" -DCMAKE_C_COMPILER="$PWD/tools/bin/zig-cc.cmd" -DCMAKE_CXX_COMPILER="$PWD/tools/bin/zig-cxx.cmd" -DMS_UI_OPEN_CONTROL_ROOT="$PWD/.tmp/l1-topology-20260926/bench/open-control" -DMS_UI_LVGL_DIR="$PWD/midi-studio/core/.pio/libdeps/dev/lvgl"
tools/cmake/bin/cmake.exe --build .tmp/l3-ui-review --parallel 8
tools/cmake/bin/ctest.exe --test-dir .tmp/l3-ui-review --output-on-failure
```

Précisions sur les preuves :
- `--check` topologie refuse normalement le worktree L1 tant que le correctif n'est pas commité. Pendant cette correction, appel direct de `build_inventory()` et comparaison `structural_diff()` avec le snapshot du bench L1 : **aucune différence**. Rejouer le vrai `--check` après intégration sur arbre propre ; le garde de propreté n'a pas été changé.
- Mutation L6 compilée dans un répertoire temporaire : ajouter `oldMode`, publier `policy::MODES[appliedIndex]` avant `store_->commitStatus()`, restaurer `oldMode` sur échec. Le binaire lié au vrai test échoue dans `assertModeNotPublished()` ; baseline verte. Le script de cette session est dans `%LOCALAPPDATA%/Temp/opencode/review_l6_mutation.py`.
- Ruff appliqué au script Core complet relève des écarts préexistants (imports, longues lignes, `zip`, etc.) ; ne pas annoncer ce contrôle global vert. Les contrôles spécifiques de topologie et `git diff --check` des correctifs passent.
- CTest UI fournit maintenant une commande locale reproductible ; ni le catalogue `ms test` ni une CI UI n'ont été ajoutés. Raccorder la commande CTest à la CI produit avec les dépendances épinglées avant de considérer la couverture automatique acquise.
- Les tests headless emploient les polices LVGL intégrées. Restent avant clôture L3 : captures comparatives des sélecteurs dans Core/Bitwig avec assets réels (ouverture, défilement, réduction, réouverture), puis validation visuelle. L2 page/device→batch et Java restent ouverts.

Ordre immédiat : intégrer les trois correctifs → mettre à jour la pile Core → qualification visuelle L3 et raccordement CI → atterrissage selon la section dédiée → régénération coordonnée du snapshot/pins → validations sur les révisions mergées. La clôture documentaire L7 suivra ces preuves.

### Intégration, qualification visuelle et L7 — 2026-09-26

Cette entrée remplace les actions restantes de l'entrée précédente.

- Correctifs commités/poussés : Core L1 `286d802a` (parseur), `7c710f46` (hash du script dans le snapshot) ; Core L6 `c186529f` (ordre persistance/publication et écritures) ; UI `e638bc2` (CTest et CI).
- La pile Core a été mise à jour par merges ordinaires, sans force-push.
- CI UI ajoutée dans `.github/workflows/ci.yml` : GCC/Linux, Release avec assertions actives, deux exécutables CTest et dépendances épinglées aux révisions qualifiées Core. Run [36235971136](https://github.com/petitechose-midi-studio/ui/actions/runs/36235971136) **SUCCESS**, 40 s.
- UI #15 mergée : `fc0fe91ad7aab1510c3e9a8ee475f91e41e64918`.
- Bitwig #28 mergée : `f56e89d` ; #29 remise à jour avec `main`, puis CI [36236480471](https://github.com/petitechose-midi-studio/plugin-bitwig/actions/runs/36236480471) **SUCCESS**, 3 min 52 s, firmware release et extension. #29 mergée : `8bc9a7f3fafb7746372349339effb24efe9c1c18`.
- Pins de qualification Core alignés sur ces deux merges (`4eb0c470`), snapshot recalculé et commité (`a83fdb17`), puis propagés aux branches L4/L5/L6. Vrai `--check` sur le bench propre `.tmp/product-landing-bench` : **PASS**.
- Onboarding produit livré : Core `docs/DEVELOPER_ONBOARDING.md` (`d2c46d48`) ; README Bitwig (`d256ff6`) ; README UI inclus dans `e638bc2`. Propriétaires, adaptateurs, garanties exécutables et commandes sont explicités sans recopier les roadmaps.

**Qualification L3 :** le seul consommateur Bitwig migré est `ViewSelector` via `BaseSelector`. Les sélecteurs pages/devices/tracks utilisent leurs composants dédiés ; le sélecteur Core utilise aussi un autre composant.

1. Harnais compilant le vrai `ViewSelector` avant (`f872b345`) et après (`b188c7a`), avec les six polices binaires produit chargées : **7 paires de captures identiques octet par octet** (ouverture, dernier élément, défilement de 12 lignes, réduction à une ligne, masquage, réouverture, destruction).
2. Application Bitwig SDL réelle : hook temporaire sur les signaux publics `BitwigContext::state().viewSelector` ; contexte, abonnements et composants réels. **4 paires avant/après identiques pixel par pixel** (ouverture, sélection, masquage, réouverture).
3. Capture Core SDL `--capture-scenario view-selector` réalisée et inspectée ; textes/icônes/sélection visibles. Les comparaisons Bitwig ont également été inspectées visuellement.
4. Preuves et sources du harnais : `.tmp/l3-visual-qualification/README.md`, `comparison.png`, `simulators.png`, `manifest.json` ; archive `.tmp/l3-visual-evidence.zip`. Le CMake SDL a été remis sur l'entrée native normale et reconstruit après les captures.

Une première tentative headless sans support des polices compressées produisait des glyphes absents : elle a été rejetée. Les preuves retenues activent `LV_USE_FONT_COMPRESSED=1`, comme le produit, et affichent effectivement les polices. Cette qualification ne couvre ni les échanges avec Bitwig Studio ni le matériel Teensy.

**Atterrissage Core terminé :** `.tmp/land-core-stack.py` a intégré #178 → #179 → #180 → #181, après mise à jour avec `main`, succès de la CI associée au SHA exact et merge protégé de ce HEAD. L'attente a été corrigée pour supporter le retard des checks après push et du reciblage automatique après merge.

| PR Core | Commit de merge |
| --- | --- |
| #178 | `584b4398717bc530b31cf0d36c218aeaf02cf09f` |
| #179 | `11563eed5766ef7a81efed74bb2b6dbd2582602b` |
| #180 | `9743f8e5c58616b48fedecd745de99757940c8df` |
| #181 | `b61e0b9158f6e1cc7677794f709caf6c4c59196d` |

CI finale de #181 : [36238014167](https://github.com/petitechose-midi-studio/core/actions/runs/36238014167), **SUCCESS** : firmware release, tests natifs, SDL WASM, SDL native avec AddressSanitizer et parcours de durée de vie UI, agrégat `unit tests`.

Validation locale des commits mergés terminée avec `.tmp/validate-product-landing.ps1` dans `.tmp/product-final-bench` : **PASS**. Core **206/206** (187,40 s), Bitwig **2/2** (8,60 s), UI **2/2** (CTest 0,36 s), architecture et vrai `--check` topologie OK. Les suites L2 (Java, décision sur l'offset de modulation pré-batch) et L6 (autres familles textuelles) restent ouvertes.

### Suite : couverture page/device et suppression des checks redondants

- Bitwig : branche `codex/bitwig-page-batch-cleanup`, commit `bcdc8f4`, [PR #30](https://github.com/petitechose-midi-studio/plugin-bitwig/pull/30), worktree `.worktrees/bitwig-page-batch-cleanup`. Le scénario passe par le vrai protocole binaire et les handlers device/page/paramètres : invalidation du cache, loading des huit slots, remplacement des noms/types/listes/visibilité, batch dirty/echo, puis seconde page avec une autre cardinalité de liste.
- Dépendances retirées : état global et API encodeur physique des handlers page/device concernés, import des polices/LVGL depuis les constantes d'état, deuxième passe d'initialisation des types dans PageHostHandler. Le port encodeur existant est réutilisé ; aucun adaptateur de compatibilité ajouté.
- Bitwig : `ms --workspace .tmp/cleanup-bench test plugin-bitwig` **2/2** ; build SDL application complet **PASS**. Deux mutations testées puis retirées : suppression du loading device et cardinalité de liste incorrecte, toutes deux détectées par le nouveau scénario alors que les cinq scénarios antérieurs passent.
- Core : branche `codex/core-contract-cleanup`, commit `ea636e5a`, [PR #182](https://github.com/petitechose-midi-studio/core/pull/182), worktree `.worktrees/core-contract-cleanup`. Suppression des inspections textuelles redondantes pour l'ordre acceptation/fermeture, l'initialisation du service Project, le nombre d'appels NAV/OPT, le texte d'erreur, la ligne Clock et les noms/contenus des tests Project/ViewSwitcher. Les contrôles de frontières/ownership encore nécessaires restent explicites.
- Preuves Core : six exécutables ciblés **6/6**, architecture **OK**. `test_ModalSelectionUtils` observe désormais la pile pendant `apply` ; mutants fermeture avant acceptation et rejet ignoré détectés, retirés, puis test normal **PASS**. Les preuves existantes ProjectHandler/MenuModel/HistoryCoordinator/ViewSwitcher s'exécutent plutôt que d'être reconnues par leurs chaînes de caractères.
- Bitwig #30 mergée : `ced775e8d4c4467bdffdcf556ad689fe9efeaaf1`. CI [36239514350](https://github.com/petitechose-midi-studio/plugin-bitwig/actions/runs/36239514350) **SUCCESS**, 3 min 49 s : tests natifs, firmware release et extension.
- Pin Bitwig Core actualisé dans `ed487bd0`, snapshot coordonné dans `40f55523`. Vrai `--check` sur `.tmp/cleanup-promote-bench` propre : **PASS**. Le bench historique `.tmp/core-contract-pin-bench` conserve l'ancien Bitwig et ne représente plus les pins courants.
- Core #182 mergée : `0644610488633c61612d5c9248c8e10eaaf7ed36`. CI finale [36239786393](https://github.com/petitechose-midi-studio/core/actions/runs/36239786393) **SUCCESS** : firmware release, tests natifs, SDL native/AddressSanitizer et parcours UI, SDL WASM, agrégat `unit tests`. Le run précédent `36239514454` a été annulé par la mise à jour des pins ; il ne qualifie pas le HEAD final.
- `git diff --exit-code` confirme les arbres identiques entre chaque HEAD qualifié et son merge : Core `40f55523` → `06446104`, Bitwig `bcdc8f4` → `ced775e8`. Les validations locales et CI ci-dessus portent donc sur le contenu intégré.
- Suite ordonnée : migrer les garanties settlement, clip-workspace et le câblage des consommateurs de sélecteurs ; compléter la suite métier Java et décider du comportement de modulation pré-batch. Chaque retrait de check doit référencer sa preuve exécutable ; ne pas conserver de shim ou de double chemin après migration.

### Suite L6 : ClipWorkspace — intégré et qualifié

- Branche `codex/core-clip-contracts`, worktree `.worktrees/core-clip-contracts`, base mergée `06446104`, bench `.tmp/clip-contract-bench` aux pins coordonnés de #182.
- Quatre checks textuels ClipWorkspace remplacés par la suite `test_SequencerStepHandler` : création/mute sur en-tête, Stop momentané sur BOTTOM_LEFT, ouverture de l'éditeur et sélection de piste. Le check « long action » décrivait mal le câblage actuel de l'éditeur : l'entrée physique testée est le relâchement LEFT_CENTER ; NAV long démarre la sélection.
- Le nouveau test a échoué sur le produit initial : viser la piste 1 avec la piste 0 active puis maintenir NAV sélectionnait la piste 0. Correction : une seule implémentation `SequencerStructureNavigationWorkflow::enterTrackSelection(track)` ; ClipWorkspace lui passe la piste focalisée, la route de focus courant lui passe la piste active. Aucun changement de piste active ni mute à l'entrée en sélection.
- Couverture complémentaire : piste désactivée non sélectionnable, Add header sans éditeur de l'ancienne piste, éditeur ouvert sur la piste focalisée, sélection/Remove exclusive du Stop, assertions après drainage des notifications.
- Preuves déjà acquises : scénario nouveau rouge avant correction puis suite SequencerStepHandler verte ; cinq mutants retirés après détection (création supprimée, mute supprimé, entrée Stop supprimée, sortie Stop supprimée, éditeur supprimé). Architecture **OK** après suppression des quatre checks et de leur constante morte.
- Suite Core complète après restauration des mutants et ajout des derniers cas négatifs : **206/206**, 141,80 s. Topologie sur bench propre après commit : **PASS**. Onboarding Core actualisé pour pointer vers la preuve physique et le ciblage explicite.
- [PR Core #183](https://github.com/petitechose-midi-studio/core/pull/183) mergée : `ce08cb2f66877ba281a8b7b2a68c65eda88689a2`. CI [36242195609](https://github.com/petitechose-midi-studio/core/actions/runs/36242195609) **SUCCESS** : tests natifs, firmware release, SDL native avec AddressSanitizer et parcours UI, SDL WASM, agrégat `unit tests`.
- `git diff --exit-code` confirme l'arbre identique entre le HEAD qualifié `6dfd8d7c` et le merge `ce08cb2f`. Ce lot est clôturé ; les migrations settlement/câblage des sélecteurs et la couverture Java restent ouvertes.

### Suite autonome — settlement, consommateurs de sélecteurs et Java (2026-09-27)

- **Settlement intégré** : [Core #184](https://github.com/petitechose-midi-studio/core/pull/184), commit `fa1e897b`, merge `cecbf9e50bb767864d9e75ed3fa3d66910757915`, arbres identiques vérifiés. CI `36303435815` entièrement verte (firmware, native, SDL ASan/UI, WASM, agrégat). Local : **206/206**, 151,84 s, architecture/topologie PASS.
- `test_SequencerStepHandler` couvre le rejet Step via API publique : hold observé pendant commit et conservé après rollback ; succès puis collage identique terminent le geste, sans nouvelle écriture/abort pour le no-op. Trois inspections du builder/helper et table de routage supprimées. Mutants détectés puis retirés : exécution supprimée, NoChange→Failed, rejet Step finalisé comme un succès.
- **Consommateurs de sélecteurs publiés** : [Core #185](https://github.com/petitechose-midi-studio/core/pull/185), branche `codex/core-selector-contracts` dans `.worktrees/core-settlement-contracts`. Inspections textuelles de Device/Macro/Pitch, retour littéral de persistance et constante morte retirés. Trois consommateurs déconnectés → trois suites rouges ; rejet Device ignoré → rouge ; restauration → **4/4** suites vertes et architecture PASS. CI/intégration à consigner.
- **Java publié** : [Bitwig #31](https://github.com/petitechose-midi-studio/plugin-bitwig/pull/31), `d6f64d6`, worktree `.worktrees/bitwig-java-contracts`. JUnit/Mockito/Surefire, quatre scénarios du vrai `DeviceHost` avec observateurs capturés et tâches pilotées, sans instance Bitwig ni sleep. Maven `clean package` **4/4**, extension produite dans `.tmp/qualified-java-extension`, CI archive Surefire.
- Défaut découvert par la suite Java : remplacement de page suivi d'un batch pouvait réémettre l'ancien display/echo. Snapshot de page synchronise désormais display et efface les masques remplacés. Mutants garde de vue supprimée et masques non réinitialisés détectés puis retirés. Calcul firmware de modulation pré-batch inchangé.
- Les anciens benches `.tmp` n'étaient plus présents à la reprise. Bench reconstruit `.tmp/settlement-contract-bench` depuis les SHA exacts de la CI #184 (worktrees détachés pour les dépendances, Core lié au worktree isolé). Aucune dépendance au WIP des checkouts principaux.
- Allègement supplémentaire préparé dans #185 : inventaire automatique >800 lignes, option `--inventory`, appel Git/lecture intégrale dédiée et références documentaires supprimés ; deux autres constantes mortes retirées. La règle de revue garde les responsabilités/points de changement comme critère. Architecture PASS après retrait.
- Package Java inspecté : aucune classe de test, JUnit ou Mockito dans `.bwextension`. Les quatre scénarios sont exécutés lors de `package`, les dépendances restent de scope `test`.
- **Java intégré** : #31 mergée en `2a6beaf075d5250e5083aa9fa4850f5148a0c9d8`, arbre identique au HEAD qualifié `d6f64d6`. CI `36303953562` verte en 4m49s ; logs vérifiés : **2/2 natifs et 4/4 Java**, aucun test Java skippé, firmware release et extension produits.
- **Promotion finale Core publiée** : #185 HEAD `c999101e`, inclut retrait inventaire `8ca2516a`, pin Bitwig `9346b780`, snapshot `c999101e`. Snapshot examiné : seuls hash CI et identité Bitwig changent ; inventaires C++ inchangés. `--check` sur bench propre **PASS**. Suivi CI/merge protégé lancé sur le SHA exact.
- **Promotion finale intégrée** : [Core #185](https://github.com/petitechose-midi-studio/core/pull/185) mergée en `9cb245bafc225def966a86bdb99c2ff1562b2311`. CI `36304271082` entièrement verte : native tests, firmware release, SDL native ASan/parcours UI, SDL WASM et agrégat `unit tests`. Arbre du merge identique au HEAD qualifié `c999101e`, vérifié après fetch.
- **Clôture de cette continuation** : les trois livraisons annoncées (settlement du collage, consommateurs de sélecteurs de valeurs, suite métier Java) sont intégrées. Aucun traitement de cette session en cours. Révisions coordonnées : Core `9cb245ba`, Bitwig `2a6beaf`, UI `fc0fe91`.
- **Périmètre restant distinct** : les autres familles de contrôles statiques Core n'ont pas toutes été migrées ; cette clôture ne signifie pas suppression exhaustive du legacy. La restructuration Python E4 reste dans sa feuille de route. Décision de modulation firmware pré-batch et qualification Bitwig Studio/Teensy restent ouvertes.
