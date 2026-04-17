from __future__ import annotations

from ms.release.infra.repos.app import (
    AppRepoPaths,
    ensure_app_repo,
)
from ms.release.infra.repos.app import (
    checkout_main_and_pull as checkout_app_main_and_pull,
)
from ms.release.infra.repos.app import commit_and_push as commit_app_and_push
from ms.release.infra.repos.app import create_branch as create_app_branch
from ms.release.infra.repos.app import (
    ensure_clean_git_repo as ensure_clean_app_repo,
)
from ms.release.infra.repos.app import merge_pr as merge_app_pr
from ms.release.infra.repos.app import open_pr as open_app_pr
from ms.release.infra.repos.core import CoreRepoPaths, ensure_core_repo
from ms.release.infra.repos.core import checkout_main_and_pull as checkout_core_main_and_pull
from ms.release.infra.repos.core import commit_and_push as commit_core_and_push
from ms.release.infra.repos.core import create_branch as create_core_branch
from ms.release.infra.repos.core import ensure_clean_git_repo as ensure_clean_core_repo
from ms.release.infra.repos.core import merge_pr as merge_core_pr
from ms.release.infra.repos.core import open_pr as open_core_pr
from ms.release.infra.repos.distribution import (
    DistRepoPaths,
    ensure_distribution_repo,
)
from ms.release.infra.repos.distribution import (
    checkout_main_and_pull as checkout_distribution_main_and_pull,
)
from ms.release.infra.repos.distribution import commit_and_push as commit_distribution_and_push
from ms.release.infra.repos.distribution import create_branch as create_distribution_branch
from ms.release.infra.repos.distribution import (
    ensure_clean_git_repo as ensure_clean_distribution_repo,
)
from ms.release.infra.repos.distribution import merge_pr as merge_distribution_pr
from ms.release.infra.repos.distribution import open_pr as open_distribution_pr
from ms.release.infra.repos.git_ops import run_git_command

__all__ = [
    "AppRepoPaths",
    "CoreRepoPaths",
    "DistRepoPaths",
    "checkout_app_main_and_pull",
    "checkout_core_main_and_pull",
    "checkout_distribution_main_and_pull",
    "commit_app_and_push",
    "commit_core_and_push",
    "commit_distribution_and_push",
    "create_app_branch",
    "create_core_branch",
    "create_distribution_branch",
    "ensure_app_repo",
    "ensure_clean_app_repo",
    "ensure_clean_core_repo",
    "ensure_clean_distribution_repo",
    "ensure_core_repo",
    "ensure_distribution_repo",
    "merge_app_pr",
    "merge_core_pr",
    "merge_distribution_pr",
    "open_app_pr",
    "open_core_pr",
    "open_distribution_pr",
    "run_git_command",
]
