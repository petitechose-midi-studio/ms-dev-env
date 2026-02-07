from __future__ import annotations

from pathlib import Path

from ms.core.result import Result
from ms.platform.files import atomic_write_text
from ms.release.domain.models import PinnedRepo, ReleaseChannel
from ms.release.errors import ReleaseError
from ms.release.infra.artifacts import spec_writer as _spec_writer
from ms.release.infra.artifacts.spec_writer import WrittenSpec, spec_path_for_tag


def write_release_spec(
    *,
    dist_repo_root: Path,
    channel: ReleaseChannel,
    tag: str,
    pinned: tuple[PinnedRepo, ...],
) -> Result[WrittenSpec, ReleaseError]:
    original_write = _spec_writer.atomic_write_text
    _spec_writer.atomic_write_text = atomic_write_text
    try:
        return _spec_writer.write_release_spec(
            dist_repo_root=dist_repo_root,
            channel=channel,
            tag=tag,
            pinned=pinned,
        )
    finally:
        _spec_writer.atomic_write_text = original_write


__all__ = ["WrittenSpec", "spec_path_for_tag", "write_release_spec"]
