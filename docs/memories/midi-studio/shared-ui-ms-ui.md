# MIDI Studio - Shared UI (`ms-ui`)

`ms-ui` is the product-level shared LVGL UI library used by MIDI Studio targets.

## Repo

- Source: `midi-studio/ui`
- Namespace: `ms::ui`
- Include root: `<ms/ui/...>`

## What belongs in `ms-ui`

- Pure LVGL UI components reused across multiple targets.
- Shared UI assets that are not target-specific (ex: shared text fonts).
- Theme-neutral defaults (use `oc::ui::lvgl::base_theme` as the baseline).

## What does NOT belong in `ms-ui`

- Target themes: `StandaloneTheme`, `BitwigTheme`.
- Target state / business logic: `CoreState`, Bitwig protocol/state, DAW-specific UI.

## Current inventory

- Layout primitives:
  - `ms::ui::ViewContainer`
  - `ms::ui::LayoutOverlay`
- Overlay wiring helper:
  - `ms::ui::OverlayBindingContext`
- Fonts:
  - `ms::ui::font::CoreFonts` (+ global instance `ms::ui::font::fonts`)
- Selector overlays:
  - `ms::ui::ListOverlay`
  - `ms::ui::BaseSelector`
  - `ms::ui::StringListSelector`

## Include conventions

- Shared UI: `#include <ms/ui/...>`
- Target-local UI:
  - Core: `#include "ui/..."` (inside `midi-studio/core`)
  - Plugins: `#include "ui/..."` (inside each `midi-studio/plugin-*`)
- Never include `core` UI headers from a plugin.

## Selector pattern

- For a modal overlay that displays a list of strings, use `ms::ui::StringListSelector`.
- Pass a stable items vector via pointer:

```cpp
static const std::vector<std::string> NAMES = {"A", "B"};
selector->render({
    .items = &NAMES,
    .selectedIndex = state.selectedIndex.get(),
    .visible = state.visible.get(),
});
```

- If the list content changes (not only the selected index), call `invalidateItems()`.

## Build integration

- PlatformIO: `lib_deps` uses `ms-ui=symlink://../ui` in:
  - `midi-studio/core/platformio.ini`
  - `midi-studio/plugin-bitwig/platformio.ini`
- SDL (core desktop): `midi-studio/core/sdl/CMakeLists.txt` includes `midi-studio/ui/src`.
