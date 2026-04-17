from __future__ import annotations

from ms.release.domain.models import ReleaseBump, ReleaseChannel

from .session_models import ContentSessionStep, SessionStep


def parse_channel(value: str | None) -> ReleaseChannel | None:
    if value == "stable":
        return "stable"
    if value == "beta":
        return "beta"
    return None


def parse_bump(value: str | None) -> ReleaseBump | None:
    if value == "major":
        return "major"
    if value == "minor":
        return "minor"
    if value == "patch":
        return "patch"
    return None


def parse_app_step(value: str | None) -> SessionStep | None:
    if value == "product":
        return "product"
    if value == "channel":
        return "channel"
    if value == "bump":
        return "bump"
    if value == "tag":
        return "tag"
    if value == "sha":
        return "sha"
    if value == "notes":
        return "notes"
    if value == "summary":
        return "summary"
    if value == "confirm":
        return "confirm"
    return None


def parse_content_step(value: str | None) -> ContentSessionStep | None:
    if value == "product":
        return "product"
    if value == "channel":
        return "channel"
    if value == "bump":
        return "bump"
    if value == "repo":
        return "repo"
    if value == "bom":
        return "bom"
    if value == "tag":
        return "tag"
    if value == "notes":
        return "notes"
    if value == "summary":
        return "summary"
    if value == "confirm":
        return "confirm"
    return None


def get_int(record: dict[str, object], *, name: str, default: int) -> int:
    value = record.get(name)
    return value if isinstance(value, int) else default
