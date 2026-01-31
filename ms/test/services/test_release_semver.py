from __future__ import annotations

from ms.services.release.semver import SemVer, format_beta_tag, parse_beta_tag, parse_stable_tag


def test_parse_stable_tag() -> None:
    assert parse_stable_tag("v1.2.3") == SemVer(1, 2, 3)
    assert parse_stable_tag("v0.0.1") == SemVer(0, 0, 1)


def test_parse_stable_tag_rejects_prerelease_like_tags() -> None:
    assert parse_stable_tag("v1.2.3-beta.1") is None
    assert parse_stable_tag("v0.0.0-test.3") is None
    assert parse_stable_tag("1.2.3") is None


def test_parse_beta_tag() -> None:
    parsed = parse_beta_tag("v1.2.3-beta.4")
    assert parsed == (SemVer(1, 2, 3), 4)


def test_format_beta_tag_roundtrip() -> None:
    base = SemVer(1, 0, 0)
    tag = format_beta_tag(base, 12)
    assert tag == "v1.0.0-beta.12"
    assert parse_beta_tag(tag) == (base, 12)
