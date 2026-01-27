# Phase 5a: Type-safety contract (Pyright)

**Scope**: ms Python codebase (typing + boundaries)
**Status**: started
**Created**: 2026-01-27
**Updated**: 2026-01-27

## Goal

- Keep `pyright` strict meaningful as the codebase grows.
- Prevent `Any` / `Unknown` from leaking into the core logic.
- Standardize how we ingest dynamic inputs (TOML/JSON/env/subprocess).

## Contract

Definitions:

- Boundary: any data coming from outside the typed core (TOML/JSON, env vars, CLI strings, subprocess output, filesystem).
- Typed core: services + core logic that operate on validated/typed values.

Rules:

1. Boundary values start as `object`.
   - Do not propagate `Any` from parsers (`tomllib`, `json`).
   - Convert to typed structures immediately.

2. Validate shape at the boundary.
   - Use `ms/core/structured.py` for dict/list shape checks (`as_str_dict`, `as_obj_list`) and safe access (`get_str`, `get_table`).
   - Prefer strict validation over “best-effort str(...) on everything”.

3. Typed core never consumes `dict[str, Any]`.
   - After parsing, values should be primitives, dataclasses, `Path`, or explicitly typed records.

4. `cast(...)` is allowed only:
   - inside helpers after a runtime guard, or
   - as a last resort at a boundary (prefer adding a helper).

5. Tests must not hide type issues.
   - Prefer patching module attributes (not string paths) and use typed fakes instead of `lambda *a, **k`.

## Pyright enforcement

- Baseline: `typeCheckingMode = strict` (already enabled).

- Tighten inference so we don't silently fall back to `Any` in containers:
  - `strictListInference = true`
  - `strictDictionaryInference = true`
  - `strictSetInference = true`

- Note: Pyright does not provide a config switch to forbid `typing.Any` directly.
  We enforce this contract with a small pytest guard that rejects `from typing import Any`
  and `typing.Any` usages.

## Plan (atomic)

1. `refactor(types): validate dynamic inputs with structured helpers`
   - Add `ms/core/structured.py` and refactor TOML/JSON parsing + tests to remove `Unknown` leakage.

2. `refactor(types): remove explicit Any from ms/`
   - Replace remaining `typing.Any` usage with `object`/aliases and typed callbacks.
   - Tighten config/workspace/tool pins parsing to use validated shapes.

3. `chore(pyright): tighten inference`
   - Enable strict container inference flags.
   - Ensure `pyright` remains green.

4. `test(types): forbid typing.Any`
   - Add a guard test that fails if `typing.Any` is introduced.

## Work log

- 2026-01-27:
  - Landed structured boundary helpers and removed `Unknown` propagation in parsers/tests.
  - Verified: `pyright` (0 errors), `uv run pytest ms/test -q`.

- 2026-01-27:
  - Removed explicit `typing.Any` from `ms/` (switched boundaries to validated `object`/tables).
  - Added strict container inference in pyright and a pytest guard against `typing.Any`.

## Verification (minimum)

```bash
pyright
uv run pytest ms/test -q
```

## Sources

- `ms/core/structured.py`
- `pyproject.toml` (`[tool.pyright]`)
- parsers using `tomllib` / `json`
