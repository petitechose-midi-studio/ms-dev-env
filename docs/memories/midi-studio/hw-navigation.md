# Navigation Patterns

This file captures the intended navigation conventions for MIDI Studio.
It is used as a reference by planned feature specs so mappings stay consistent.

Important invariants for input/overlay ownership are documented in:

- `midi-studio/core/docs/INVARIANTS.md`

## Conventions (intent)

- `LEFT_TOP`
  - press: back / escape / mode selector entry (depending on current view)
  - long press: breadcrumb / global escape (when implemented)

Implemented (core standalone): `LEFT_TOP` press opens the top-level View Selector overlay.

- `NAV` encoder + button
  - turn: navigate lists / change focused index
  - press: confirm / open primary settings overlay

- `OPT` encoder
  - turn: fine-tune the last-touched value (or secondary parameter)

- Bottom row
  - `BOTTOM_LEFT`: previous page / previous item group
  - `BOTTOM_CENTER`: play/pause (context-dependent)
  - `BOTTOM_RIGHT`: next page / next item group

These conventions are a contract, not a guarantee of current implementation.
