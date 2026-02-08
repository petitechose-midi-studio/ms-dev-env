from __future__ import annotations

from ms.core.result import Err, Ok, Result
from ms.release.errors import ReleaseError


def parse_override_items(items: list[str], *, flag: str) -> Result[dict[str, str], ReleaseError]:
    out: dict[str, str] = {}
    for item in items:
        if "=" not in item:
            return Err(
                ReleaseError(
                    kind="invalid_input",
                    message=f"invalid {flag} (expected id=value): {item}",
                )
            )
        key, value = item.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key or not value:
            return Err(
                ReleaseError(
                    kind="invalid_input",
                    message=f"invalid {flag} (expected id=value): {item}",
                )
            )
        out[key] = value
    return Ok(out)


def enforce_auto_constraints(
    *,
    auto: bool,
    overrides: dict[str, str],
    allow_non_green: bool,
) -> Result[None, ReleaseError]:
    if not auto:
        return Ok(None)

    if overrides:
        return Err(
            ReleaseError(
                kind="invalid_input",
                message="--auto cannot be combined with --repo overrides",
            )
        )

    if allow_non_green:
        return Err(
            ReleaseError(
                kind="invalid_input",
                message="--auto is strict: remove --allow-non-green",
            )
        )

    return Ok(None)
