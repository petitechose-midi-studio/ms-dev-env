from __future__ import annotations

from ms.services.release.model import ReleaseRepo


DIST_REPO_SLUG = "petitechose-midi-studio/distribution"
DIST_LOCAL_DIR = "distribution"
DIST_DEFAULT_BRANCH = "main"

DIST_SPEC_DIR = "release-specs"
DIST_NOTES_DIR = "release-notes"

DIST_PUBLISH_WORKFLOW = "publish.yml"

APP_REPO_SLUG = "petitechose-midi-studio/ms-manager"
APP_LOCAL_DIR = "ms-manager"
APP_DEFAULT_BRANCH = "main"
APP_CANDIDATE_WORKFLOW = "candidate.yml"
APP_RELEASE_WORKFLOW = "release.yml"
APP_RELEASE_ENV = "app-release"

APP_RELEASE_REPO = ReleaseRepo(
    id="ms-manager",
    slug=APP_REPO_SLUG,
    ref=APP_DEFAULT_BRANCH,
    required_ci_workflow_file=".github/workflows/ci.yml",
)


RELEASE_REPOS: tuple[ReleaseRepo, ...] = (
    ReleaseRepo(
        id="loader",
        slug="petitechose-midi-studio/loader",
        ref="main",
        required_ci_workflow_file=".github/workflows/ci.yml",
    ),
    ReleaseRepo(
        id="oc-bridge",
        slug="open-control/bridge",
        ref="main",
        required_ci_workflow_file=".github/workflows/ci.yml",
    ),
    ReleaseRepo(
        id="core",
        slug="petitechose-midi-studio/core",
        ref="main",
        required_ci_workflow_file=".github/workflows/ci.yml",
    ),
    ReleaseRepo(
        id="plugin-bitwig",
        slug="petitechose-midi-studio/plugin-bitwig",
        ref="main",
        required_ci_workflow_file=".github/workflows/ci.yml",
    ),
)
