from __future__ import annotations

from dataclasses import dataclass

from ms.core.result import Err, Ok, Result
from ms.services.release.errors import ReleaseError
from ms.services.release.model import DistributionRelease, ReleaseBump, ReleaseChannel
from ms.services.release.semver import SemVer, format_beta_tag, parse_beta_tag, parse_stable_tag


@dataclass(frozen=True, slots=True)
class ReleaseHistory:
    latest_stable: SemVer | None
    latest_beta_base: SemVer | None
    beta_max_by_base: dict[SemVer, int]
    existing_tags: frozenset[str]


def compute_history(releases: list[DistributionRelease]) -> ReleaseHistory:
    stable_versions: list[SemVer] = []
    beta_max: dict[SemVer, int] = {}
    tags: set[str] = set()

    for r in releases:
        tags.add(r.tag)

        if not r.prerelease:
            v = parse_stable_tag(r.tag)
            if v is not None:
                stable_versions.append(v)
            continue

        parsed = parse_beta_tag(r.tag)
        if parsed is None:
            continue
        base, n = parsed
        prev = beta_max.get(base)
        beta_max[base] = n if prev is None else max(prev, n)

    latest_stable = max(stable_versions) if stable_versions else None
    latest_beta_base = max(beta_max.keys()) if beta_max else None

    return ReleaseHistory(
        latest_stable=latest_stable,
        latest_beta_base=latest_beta_base,
        beta_max_by_base=beta_max,
        existing_tags=frozenset(tags),
    )


def suggest_tag(*, channel: ReleaseChannel, bump: ReleaseBump, history: ReleaseHistory) -> str:
    base0 = history.latest_stable or SemVer(0, 0, 0)
    candidate = base0.bump(bump)

    if channel == "stable":
        return candidate.to_tag()

    # beta: keep monotonic progression even if there is an existing higher beta base.
    base = candidate
    if history.latest_beta_base is not None and history.latest_beta_base > base:
        base = history.latest_beta_base

    n = history.beta_max_by_base.get(base, 0) + 1
    if n < 1:
        n = 1
    return format_beta_tag(base, n)


def validate_tag(
    *,
    channel: ReleaseChannel,
    tag: str,
    history: ReleaseHistory,
) -> Result[None, ReleaseError]:
    if tag in history.existing_tags:
        return Err(
            ReleaseError(
                kind="tag_exists",
                message=f"tag already exists: {tag}",
                hint="Pick a new version tag.",
            )
        )

    if channel == "stable":
        v = parse_stable_tag(tag)
        if v is None:
            return Err(
                ReleaseError(
                    kind="invalid_tag",
                    message=f"invalid stable tag: {tag}",
                    hint="Expected: vMAJOR.MINOR.PATCH",
                )
            )
        if history.latest_stable is not None and v <= history.latest_stable:
            return Err(
                ReleaseError(
                    kind="invalid_tag",
                    message=(
                        f"stable tag must be > latest stable ({history.latest_stable.to_tag()})"
                    ),
                    hint="Use --bump or --tag to choose a higher version.",
                )
            )
        return Ok(None)

    # beta
    parsed = parse_beta_tag(tag)
    if parsed is None:
        return Err(
            ReleaseError(
                kind="invalid_tag",
                message=f"invalid beta tag: {tag}",
                hint="Expected: vMAJOR.MINOR.PATCH-beta.N",
            )
        )

    base, n = parsed
    if n < 1:
        return Err(
            ReleaseError(
                kind="invalid_tag",
                message=f"invalid beta number in tag: {tag}",
                hint="beta.N must be >= 1",
            )
        )

    if history.latest_stable is not None and base <= history.latest_stable:
        return Err(
            ReleaseError(
                kind="invalid_tag",
                message=(
                    f"beta base version must be > latest stable ({history.latest_stable.to_tag()})"
                ),
                hint="Use --bump or --tag to choose a higher version.",
            )
        )

    if history.latest_beta_base is not None and base < history.latest_beta_base:
        return Err(
            ReleaseError(
                kind="invalid_tag",
                message=(
                    "beta base version must be >= latest beta base "
                    f"({history.latest_beta_base.to_tag()})"
                ),
                hint="Use --tag to continue the current beta base.",
            )
        )

    return Ok(None)
