from __future__ import annotations

from pathlib import Path

from ms.core.result import Err, Ok
from ms.services.repo_profiles import RepoProfile, repo_manifest_paths
from ms.services.repos.manifest import load_manifests


def test_maintainer_profile_extends_the_dev_manifest() -> None:
    dev = load_manifests(repo_manifest_paths(RepoProfile.dev))
    maintainer = load_manifests(repo_manifest_paths(RepoProfile.maintainer))

    assert isinstance(dev, Ok)
    assert isinstance(maintainer, Ok)
    assert maintainer.value[: len(dev.value)] == dev.value
    assert any(spec.name == "ms-manager" for spec in maintainer.value)


def test_composed_manifests_reject_duplicate_repositories(tmp_path: Path) -> None:
    manifest = """\
[[repos]]
org = "open-control"
name = "framework"
url = "https://github.com/open-control/framework"
path = "open-control/framework"
branch = "main"
"""
    first = tmp_path / "first.toml"
    second = tmp_path / "second.toml"
    first.write_text(manifest, encoding="utf-8")
    second.write_text(manifest, encoding="utf-8")

    result = load_manifests((first, second))

    assert isinstance(result, Err)
    assert result.error.message == "duplicate repo in manifests: open-control/framework"


def test_manifest_rejects_incomplete_entries(tmp_path: Path) -> None:
    manifest = tmp_path / "repos.toml"
    manifest.write_text(
        """\
[[repos]]
org = "open-control"
name = "framework"
path = "open-control/framework"
""",
        encoding="utf-8",
    )

    result = load_manifests((manifest,))

    assert isinstance(result, Err)
    assert result.error.message == "repo manifest entry 0 missing required field: url"
