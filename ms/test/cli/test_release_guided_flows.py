from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from ms.cli.selector import SelectorResult
from ms.core.result import Ok
from ms.output.console import MockConsole
from ms.services.release.service import AppPrepareResult
from ms.services.release.wizard_session import (
    AppReleaseSession,
    ContentReleaseSession,
    new_app_session,
    new_content_session,
)


def _sel(value: str, index: int = 0) -> SelectorResult[str]:
    return SelectorResult(action="select", value=value, index=index)


def test_guided_app_happy_path(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    import ms.cli.release_guided_app as app

    session = new_app_session(created_by="alice", notes_path=None)
    session = replace(
        session, notes_path="/tmp/notes.md", notes_markdown="hello notes", notes_sha256="f" * 64
    )

    def fake_preflight(*args: object, **kwargs: object):
        return Ok("alice")

    def fake_bootstrap(*args: object, **kwargs: object):
        return Ok(session)

    def fake_save_state(*args: object, **kwargs: object):
        s = kwargs.get("session")
        assert isinstance(s, AppReleaseSession)
        return Ok(s)

    def fake_channel(*args: object, **kwargs: object):
        return _sel("stable")

    def fake_bump(*args: object, **kwargs: object):
        return _sel("patch")

    def fake_green(*args: object, **kwargs: object):
        return Ok(_sel("a" * 40))

    def fake_plan(*args: object, **kwargs: object):
        return Ok(("v1.2.3", "1.2.3"))

    summary_calls = {"count": 0}

    def fake_select_one(*args: object, **kwargs: object) -> SelectorResult[str]:
        title = str(kwargs.get("title", ""))
        if title == "Release Tag":
            return _sel("accept")
        if title == "App Release Summary":
            summary_calls["count"] += 1
            return _sel("start", index=5)
        raise AssertionError(f"unexpected selector title: {title}")

    def fake_confirm(*args: object, **kwargs: object) -> bool:
        return True

    def fake_ci_green(*args: object, **kwargs: object):
        return Ok(None)

    def fake_prepare(*args: object, **kwargs: object):
        return Ok(AppPrepareResult(pr_url="https://example/pr/1", source_sha="b" * 40))

    published: dict[str, object] = {}

    def fake_publish(*args: object, **kwargs: object):
        published.update(kwargs)
        return Ok(("https://example/candidate", "https://example/release"))

    def fake_clear(*args: object, **kwargs: object):
        return Ok(None)

    monkeypatch.setattr(app, "preflight_with_permission", fake_preflight)
    monkeypatch.setattr(app, "bootstrap_app_session", fake_bootstrap)
    monkeypatch.setattr(app, "save_app_state", fake_save_state)
    monkeypatch.setattr(app, "select_channel", fake_channel)
    monkeypatch.setattr(app, "select_bump", fake_bump)
    monkeypatch.setattr(app, "select_green_commit", fake_green)
    monkeypatch.setattr(app, "plan_app_release", fake_plan)
    monkeypatch.setattr(app, "select_one", fake_select_one)
    monkeypatch.setattr(app, "confirm_yn", fake_confirm)
    monkeypatch.setattr(app, "ensure_ci_green", fake_ci_green)
    monkeypatch.setattr(app, "prepare_app_pr", fake_prepare)
    monkeypatch.setattr(app, "publish_app_release", fake_publish)
    monkeypatch.setattr(app, "clear_app_session", fake_clear)

    result = app.run_guided_app_release(
        workspace_root=tmp_path,
        console=MockConsole(),
        notes_file=None,
        watch=False,
        dry_run=True,
    )

    assert isinstance(result, Ok)
    assert summary_calls["count"] == 1
    assert published["tag"] == "v1.2.3"
    assert published["source_sha"] == "b" * 40
    assert published["notes_markdown"] == "hello notes"
    assert published["notes_source_path"] == "/tmp/notes.md"


def test_guided_app_summary_edit_recomputes_tag(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import ms.cli.release_guided_app as app

    session = new_app_session(created_by="alice", notes_path=None)

    def fake_preflight(*args: object, **kwargs: object):
        return Ok("alice")

    def fake_bootstrap(*args: object, **kwargs: object):
        return Ok(session)

    def fake_save_state(*args: object, **kwargs: object):
        s = kwargs.get("session")
        assert isinstance(s, AppReleaseSession)
        return Ok(s)

    channel_calls = {"count": 0}

    def fake_channel(*args: object, **kwargs: object):
        channel_calls["count"] += 1
        return _sel("stable")

    def fake_bump(*args: object, **kwargs: object):
        return _sel("patch")

    def fake_green(*args: object, **kwargs: object):
        return Ok(_sel("a" * 40))

    tag_calls = {"count": 0}

    def fake_plan(*args: object, **kwargs: object):
        tag_calls["count"] += 1
        return Ok(("v1.2.3", "1.2.3"))

    summary_seq = [_sel("channel", index=0), _sel("start", index=5), _sel("start", index=5)]
    tag_seq = [_sel("accept"), _sel("accept")]

    def fake_select_one(*args: object, **kwargs: object) -> SelectorResult[str]:
        title = str(kwargs.get("title", ""))
        if title == "Release Tag":
            return tag_seq.pop(0)
        if title == "App Release Summary":
            return summary_seq.pop(0)
        raise AssertionError(f"unexpected selector title: {title}")

    def fake_confirm(*args: object, **kwargs: object) -> bool:
        return True

    def fake_ci_green(*args: object, **kwargs: object):
        return Ok(None)

    def fake_prepare(*args: object, **kwargs: object):
        return Ok(AppPrepareResult(pr_url="https://example/pr/2", source_sha="b" * 40))

    def fake_publish(*args: object, **kwargs: object):
        return Ok(("c", "r"))

    def fake_clear(*args: object, **kwargs: object):
        return Ok(None)

    monkeypatch.setattr(app, "preflight_with_permission", fake_preflight)
    monkeypatch.setattr(app, "bootstrap_app_session", fake_bootstrap)
    monkeypatch.setattr(app, "save_app_state", fake_save_state)
    monkeypatch.setattr(app, "select_channel", fake_channel)
    monkeypatch.setattr(app, "select_bump", fake_bump)
    monkeypatch.setattr(app, "select_green_commit", fake_green)
    monkeypatch.setattr(app, "plan_app_release", fake_plan)
    monkeypatch.setattr(app, "select_one", fake_select_one)
    monkeypatch.setattr(app, "confirm_yn", fake_confirm)
    monkeypatch.setattr(app, "ensure_ci_green", fake_ci_green)
    monkeypatch.setattr(app, "prepare_app_pr", fake_prepare)
    monkeypatch.setattr(app, "publish_app_release", fake_publish)
    monkeypatch.setattr(app, "clear_app_session", fake_clear)

    result = app.run_guided_app_release(
        workspace_root=tmp_path,
        console=MockConsole(),
        notes_file=None,
        watch=False,
        dry_run=True,
    )

    assert isinstance(result, Ok)
    assert channel_calls["count"] == 2
    assert tag_calls["count"] == 2


def test_guided_content_happy_path(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    import ms.cli.release_guided_content as content

    session = new_content_session(created_by="alice", notes_path=None)

    def fake_preflight(*args: object, **kwargs: object):
        return Ok("alice")

    def fake_bootstrap(*args: object, **kwargs: object):
        return Ok(session)

    def fake_save_state(*args: object, **kwargs: object):
        s = kwargs.get("session")
        assert isinstance(s, ContentReleaseSession)
        return Ok(s)

    def fake_channel(*args: object, **kwargs: object):
        return _sel("stable")

    def fake_bump(*args: object, **kwargs: object):
        return _sel("patch")

    select_calls: list[str] = []
    sha_map = {
        "petitechose-midi-studio/loader": "1" * 40,
        "open-control/bridge": "2" * 40,
        "petitechose-midi-studio/core": "3" * 40,
        "petitechose-midi-studio/plugin-bitwig": "4" * 40,
    }

    def fake_green(*args: object, **kwargs: object):
        repo = str(kwargs["repo_slug"])
        select_calls.append(repo)
        return Ok(_sel(sha_map[repo]))

    def fake_plan(*args: object, **kwargs: object):
        return Ok(SimpleNamespace(tag="v9.9.9", spec_path="release-specs/v9.9.9.json"))

    def fake_select_one(*args: object, **kwargs: object) -> SelectorResult[str]:
        title = str(kwargs.get("title", ""))
        if title == "Content Release Tag":
            return _sel("accept")
        if title == "Content Release Summary":
            return _sel("start", index=8)
        raise AssertionError(f"unexpected selector title: {title}")

    def fake_confirm(*args: object, **kwargs: object) -> bool:
        return True

    def fake_ci_green(*args: object, **kwargs: object):
        return Ok(None)

    def fake_open_control(*args: object, **kwargs: object):
        def _dirty_repos() -> list[str]:
            return []

        return SimpleNamespace(dirty_repos=_dirty_repos)

    def fake_prepare(*args: object, **kwargs: object):
        return Ok("https://example/pr/3")

    published: dict[str, object] = {}

    def fake_publish(*args: object, **kwargs: object):
        published.update(kwargs)
        return Ok("https://example/workflow/1")

    def fake_clear(*args: object, **kwargs: object):
        return Ok(None)

    monkeypatch.setattr(content, "preflight_with_permission", fake_preflight)
    monkeypatch.setattr(content, "bootstrap_content_session", fake_bootstrap)
    monkeypatch.setattr(content, "save_content_state", fake_save_state)
    monkeypatch.setattr(content, "select_channel", fake_channel)
    monkeypatch.setattr(content, "select_bump", fake_bump)
    monkeypatch.setattr(content, "select_green_commit", fake_green)
    monkeypatch.setattr(content, "plan_release", fake_plan)
    monkeypatch.setattr(content, "select_one", fake_select_one)
    monkeypatch.setattr(content, "confirm_yn", fake_confirm)
    monkeypatch.setattr(content, "ensure_ci_green", fake_ci_green)
    monkeypatch.setattr(content, "preflight_open_control", fake_open_control)
    monkeypatch.setattr(content, "prepare_distribution_pr", fake_prepare)
    monkeypatch.setattr(content, "publish_distribution_release", fake_publish)
    monkeypatch.setattr(content, "clear_content_session", fake_clear)

    result = content.run_guided_content_release(
        workspace_root=tmp_path,
        console=MockConsole(),
        notes_file=None,
        watch=False,
        dry_run=True,
    )

    assert isinstance(result, Ok)
    assert select_calls == [
        "petitechose-midi-studio/loader",
        "open-control/bridge",
        "petitechose-midi-studio/core",
        "petitechose-midi-studio/plugin-bitwig",
    ]
    plan_obj = published["plan"]
    assert isinstance(plan_obj, SimpleNamespace)
    assert plan_obj.tag == "v9.9.9"


def test_release_guided_routes_by_product(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    import ms.cli.release_guided as guided

    def fake_tty() -> bool:
        return True

    calls: list[str] = []

    def fake_app(*args: object, **kwargs: object):
        calls.append("app")
        return Ok(None)

    def fake_content(*args: object, **kwargs: object):
        calls.append("content")
        return Ok(None)

    monkeypatch.setattr(guided, "is_interactive_terminal", fake_tty)
    monkeypatch.setattr(guided, "run_guided_app_release", fake_app)
    monkeypatch.setattr(guided, "run_guided_content_release", fake_content)

    def fake_select_content(*args: object, **kwargs: object) -> SelectorResult[str]:
        return _sel("content")

    monkeypatch.setattr(guided, "select_one", fake_select_content)

    res_content = guided.run_guided_release(
        workspace_root=tmp_path,
        console=MockConsole(),
        notes_file=None,
        watch=False,
        dry_run=True,
    )
    assert isinstance(res_content, Ok)

    def fake_select_app(*args: object, **kwargs: object) -> SelectorResult[str]:
        return _sel("app")

    monkeypatch.setattr(guided, "select_one", fake_select_app)
    res_app = guided.run_guided_release(
        workspace_root=tmp_path,
        console=MockConsole(),
        notes_file=None,
        watch=False,
        dry_run=True,
    )
    assert isinstance(res_app, Ok)
    assert calls == ["content", "app"]
