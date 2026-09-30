from pathlib import Path
from typing import Never

from ms.core.result import Ok
from ms.release.flow.guided.content_summary_step import step_content_summary
from ms.release.flow.guided.fsm import StepAdvance
from ms.release.flow.guided.selection import Selection
from ms.release.flow.guided.session_models import new_content_session


def test_start_without_tag_returns_to_tag_and_preserves_summary_cursor(tmp_path: Path) -> None:
    class SummaryInputs:
        def select_menu(self, **kwargs: object) -> Selection[str]:
            return Selection(action="select", value="start", index=7)

        def preflight_open_control(self, **kwargs: object) -> Never:
            raise AssertionError("An unset Core pin must not trigger BOM inspection")

    result = step_content_summary(
        deps=SummaryInputs(),
        workspace_root=tmp_path,
        session=new_content_session(created_by="test", notes_path=None),
        release_repos=(),
    )

    assert isinstance(result, Ok)
    assert isinstance(result.value, StepAdvance)
    assert result.value.session.step == "tag"
    assert result.value.session.cursor.summary == 7
    assert result.value.session.cursor.return_to_summary is True
