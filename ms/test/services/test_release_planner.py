from __future__ import annotations

from ms.core.result import Err
from ms.services.release.model import DistributionRelease
from ms.services.release.planner import compute_history, suggest_tag, validate_tag
from ms.services.release.semver import SemVer


def test_history_ignores_non_semver_tags() -> None:
    releases = [
        DistributionRelease(tag="v0.0.0-test.3", prerelease=True),
        DistributionRelease(tag="not-a-tag", prerelease=False),
        DistributionRelease(tag="v1.2.3", prerelease=False),
    ]
    h = compute_history(releases)
    assert h.latest_stable == SemVer(1, 2, 3)


def test_suggest_stable_patch_bump() -> None:
    h = compute_history([DistributionRelease(tag="v1.0.0", prerelease=False)])
    assert suggest_tag(channel="stable", bump="patch", history=h) == "v1.0.1"


def test_suggest_beta_continues_existing_beta_base_if_higher() -> None:
    releases = [
        DistributionRelease(tag="v1.0.0", prerelease=False),
        DistributionRelease(tag="v1.1.0-beta.2", prerelease=True),
    ]
    h = compute_history(releases)

    # With bump=patch, candidate base would be v1.0.1, but existing beta base is v1.1.0.
    assert suggest_tag(channel="beta", bump="patch", history=h) == "v1.1.0-beta.3"


def test_validate_tag_rejects_existing_tag() -> None:
    h = compute_history([DistributionRelease(tag="v1.0.0", prerelease=False)])
    result = validate_tag(channel="stable", tag="v1.0.0", history=h)
    assert isinstance(result, Err)
    assert result.error.kind == "tag_exists"


def test_validate_tag_rejects_stable_rollback() -> None:
    h = compute_history([DistributionRelease(tag="v1.0.1", prerelease=False)])
    result = validate_tag(channel="stable", tag="v1.0.1", history=h)
    assert isinstance(result, Err)


def test_validate_tag_rejects_beta_base_not_greater_than_latest_stable() -> None:
    h = compute_history([DistributionRelease(tag="v1.0.0", prerelease=False)])
    result = validate_tag(channel="beta", tag="v1.0.0-beta.1", history=h)
    assert isinstance(result, Err)
    assert result.error.kind == "invalid_tag"
