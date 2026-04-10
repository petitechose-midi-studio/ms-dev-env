# Feature: Local Core Features Inside Bitwig Firmware

**Scope**: midi-studio/core, midi-studio/plugin-bitwig
**Status**: planned
**Created**: 2026-03-26
**Updated**: 2026-03-26

## Objectif

Garder une trace de la direction produit / architecture suivante:

- Le sequencer et le mapping manuel des macros/CC restent des features du controleur, pas des features dependantes de Bitwig.
- Le firmware `plugin-bitwig` pourra plus tard exposer ces features locales via une combinaison / entree UI dediee.
- Quand elles sont ouvertes depuis le firmware Bitwig, l'UI doit expliciter clairement qu'il s'agit d'un mode local du controleur qui emet du MIDI, independant de Bitwig.
- Les donnees de ces features doivent rester persistantes sur la SD et partagees entre firmwares.

## Intention verrouillee

### 1. Priorite actuelle

Pour l'instant, la priorite est de faire avancer les features `core` en standalone:

- sequencer note-only usable
- mapping manuel des macros / CC
- persistance stable

Il ne faut pas deriver tout de suite vers une integration Bitwig complete.

### 2. Cible future pour `plugin-bitwig`

Plus tard, le firmware Bitwig devra permettre d'acceder a certaines features `core` sans changer leur nature:

- acces au sequencer local depuis `plugin-bitwig`
- acces aux features macros / mapping manuel depuis `plugin-bitwig`
- activation via combinaison ou point d'entree explicite
- UI marquee comme "controleur local -> MIDI OUT"

Le fonctionnement de ces features doit rester identique a celui du firmware standalone:

- pas de dependance fonctionnelle a Bitwig
- pas de source de verite cote Bitwig
- pas de couplage des patterns/sequences a un projet Bitwig

### 3. Persistance partagee entre firmwares

Les sequences et configurations sauvegardees depuis le firmware Bitwig doivent etre recuperables apres reflash d'un firmware standalone, et inversement.

Donc la direction cible est:

- memes structures de state `core`
- memes services de persistance `core`
- memes fichiers SD / memes domaines de stockage
- format partage entre `core` standalone et `plugin-bitwig`

Le firmware Bitwig doit donc, au moment de cette integration future, reutiliser les backends SD et la persistance de `core`, pas inventer une persistance parallele.

### 4. Portee du sequencer

Le sequencer n'est pas destine pour l'instant a sequencer des CC.

Portee actuelle:

- note sequencer uniquement
- emission de notes MIDI normales

Une extension vers du CC sequencing pourra etre evaluee plus tard, mais ne fait pas partie de la cible immediate.

### 5. Destination du MIDI genere

Le MIDI emis par ces features locales ne doit pas etre pense comme "Bitwig only".

La direction retenue est:

- utilisable avec Bitwig si les ports/routages le permettent
- utilisable aussi vers d'autres logiciels / sequenceurs
- utilisable aussi vers un equipement externe si la sortie materielle du controleur est exploitee

Autrement dit, le moteur local doit rester generique et oriente "MIDI OUT", pas "automation interne Bitwig".

## Consequence architecturale retenue

La bonne approche future n'est pas d'embarquer tout `StandaloneContext` dans `plugin-bitwig`.

La direction retenue est:

- garder `plugin-bitwig` comme contexte Bitwig principal
- y integrer seulement les slices locales utiles de `core`
- reutiliser `CoreState` / persistance / services / vues locales selon le besoin
- preserver l'independance fonctionnelle des features locales

## Rappels de decision

- Le sequencer local reste autonome par rapport a Bitwig.
- Les donnees restent sur SD et doivent survivre a un changement de firmware.
- L'integration future dans `plugin-bitwig` est envisagee, mais ce n'est pas la priorite immediate.
- Le sequencer reste note-only pour le moment.
