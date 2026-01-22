# Migration hal-common -> hal-embedded

**Date**: 2025-01-17
**Status**: EN COURS

## Objectif

Renommer `hal-common` en `hal-embedded` et deplacer `GpioPin` de `framework` vers `hal-embedded` pour clarifier l'architecture.

## Checklist d'execution

### Phase 1: open-control

- [ ] 1.1 Creer hal-embedded/ (copie de hal-common/)
- [ ] 1.2 Renommer namespace/paths dans hal-embedded/
- [ ] 1.3 Ajouter GpioPin.hpp dans hal-embedded/
- [ ] 1.4 Supprimer GpioPin de framework/Types.hpp
- [ ] 1.5 Mettre a jour hal-teensy imports
- [ ] 1.6 Mettre a jour tous les examples
- [ ] 1.7 Supprimer hal-common/
- [ ] 1.8 Tester build examples

### Phase 2: midi-studio

- [ ] 2.1 Mettre a jour core/
- [ ] 2.2 Mettre a jour plugin-bitwig/
- [ ] 2.3 Tester build Teensy (ms core, ms bitwig)
- [ ] 2.4 Tester build Native/WASM (ms run core, ms run bitwig)

## Fichiers impactes

### open-control/framework
- `src/oc/hal/Types.hpp` - Supprimer GpioPin

### open-control/hal-embedded (nouveau)
- `library.json`
- `src/oc/hal/embedded/GpioPin.hpp` (nouveau)
- `src/oc/hal/embedded/Types.hpp`
- `src/oc/hal/embedded/ButtonDef.hpp`
- `src/oc/hal/embedded/EncoderDef.hpp`
- `src/main.cpp`

### open-control/hal-teensy
- `src/oc/hal/teensy/ButtonController.hpp`
- `src/oc/hal/teensy/EncoderController.hpp`
- `library.json`
- `platformio.ini`

### open-control/examples
- `example-teensy41-minimal/include/Config.hpp`
- `example-teensy41-minimal/platformio.ini`
- `example-teensy41-lvgl/include/Config.hpp`
- `example-teensy41-lvgl/platformio.ini`
- `example-teensy41-02-encoders/src/main.cpp`
- `example-teensy41-02-encoders/platformio.ini`
- `example-teensy41-03-buttons/src/main.cpp`
- `example-teensy41-03-buttons/platformio.ini`
- `example-teensy41-01-midi-output/platformio.ini`

### midi-studio/core
- `src/config/platform-teensy/Hardware.hpp`
- `platformio.ini`

### midi-studio/plugin-bitwig
- `platformio.ini`

## Log d'execution

### 2025-01-17

*En attente de debut d'execution...*

