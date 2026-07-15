from __future__ import annotations

from pathlib import Path

from pytest import MonkeyPatch

from ms.core.result import Err, Ok
from ms.output.console import MockConsole
from ms.release.flow.app_prepare import prepare_app_pr


def test_prepare_app_pr_reuses_versioned_main_head(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    import ms.release.flow.app_prepare as app_prepare

    main_sha = "c" * 40

    def fake_prepare_app_repo(**_: object) -> Ok[Path]:
        return Ok(tmp_path)

    def fake_version_present(**_: object) -> Ok[bool]:
        return Ok(True)

    def fake_resolve_source(**_: object) -> Ok[str]:
        return Ok(main_sha)

    monkeypatch.setattr(app_prepare, "_prepare_app_repo", fake_prepare_app_repo)
    monkeypatch.setattr(
        app_prepare,
        "_is_app_version_already_present",
        fake_version_present,
    )
    monkeypatch.setattr(
        app_prepare,
        "_resolve_versioned_app_source_sha",
        fake_resolve_source,
    )

    prepared = prepare_app_pr(
        workspace_root=tmp_path,
        console=MockConsole(),
        tag="v1.2.3",
        version="1.2.3",
        base_sha="a" * 40,
        pinned=(),
        dry_run=False,
    )

    assert isinstance(prepared, Ok)
    assert prepared.value.source_sha == main_sha
    assert prepared.value.pr.kind == "already_merged"


def test_prepare_app_pr_uses_versioned_main_head_after_merge(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    import ms.release.flow.app_prepare as app_prepare

    changed = tmp_path / "package.json"
    main_sha = "c" * 40

    def fake_prepare_app_repo(**_: object) -> Ok[Path]:
        return Ok(tmp_path)

    def fake_version_present(**_: object) -> Ok[bool]:
        return Ok(False)

    def fake_create_branch(**_: object) -> Ok[None]:
        return Ok(None)

    def fake_changed_paths(**_: object) -> Ok[list[Path]]:
        return Ok([changed])

    def fake_commit(**_: object) -> Ok[str]:
        return Ok("b" * 40)

    def fake_open_pr(**_: object) -> Ok[str]:
        return Ok("https://example.test/pr/1")

    def fake_merge_pr(**_: object) -> Ok[None]:
        return Ok(None)

    def fake_resolve_source(**_: object) -> Ok[str]:
        return Ok(main_sha)

    monkeypatch.setattr(app_prepare, "_prepare_app_repo", fake_prepare_app_repo)
    monkeypatch.setattr(
        app_prepare,
        "_is_app_version_already_present",
        fake_version_present,
    )
    monkeypatch.setattr(app_prepare, "app_create_branch", fake_create_branch)
    monkeypatch.setattr(
        app_prepare,
        "_resolve_app_changed_paths",
        fake_changed_paths,
    )
    monkeypatch.setattr(
        app_prepare,
        "app_commit_and_push",
        fake_commit,
    )
    monkeypatch.setattr(
        app_prepare,
        "app_open_pr",
        fake_open_pr,
    )
    monkeypatch.setattr(app_prepare, "_merge_app_pr", fake_merge_pr)
    monkeypatch.setattr(
        app_prepare,
        "_resolve_versioned_app_source_sha",
        fake_resolve_source,
    )

    prepared = prepare_app_pr(
        workspace_root=tmp_path,
        console=MockConsole(),
        tag="v1.2.3",
        version="1.2.3",
        base_sha="a" * 40,
        pinned=(),
        dry_run=False,
    )

    assert isinstance(prepared, Ok)
    assert prepared.value.source_sha == main_sha
    assert prepared.value.pr.kind == "merged_pr"


def test_resolve_versioned_app_source_rejects_remote_version_mismatch(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    import ms.release.flow.app_prepare as app_prepare

    def fake_head(**_: object) -> Ok[str]:
        return Ok("c" * 40)

    def fake_package_json(**_: object) -> Ok[str]:
        return Ok('{"version":"1.2.2"}')

    monkeypatch.setattr(
        app_prepare,
        "get_ref_head_sha",
        fake_head,
    )
    monkeypatch.setattr(
        app_prepare,
        "get_repo_file_text",
        fake_package_json,
    )

    resolved = app_prepare._resolve_versioned_app_source_sha(  # pyright: ignore[reportPrivateUsage]
        workspace_root=tmp_path,
        version="1.2.3",
    )

    assert isinstance(resolved, Err)
    assert resolved.error.message == "remote app version does not match the requested release"
