from __future__ import annotations

from dataclasses import dataclass, replace

from ms.cli.release_fsm import FINISH, StepOutcome, advance, run_state_machine
from ms.core.result import Err, Ok, Result
from ms.services.release.errors import ReleaseError


@dataclass(frozen=True, slots=True)
class _State:
    step: str
    counter: int


def test_run_state_machine_advances_and_saves() -> None:
    saved: list[_State] = []

    def save_state(s: _State) -> Result[_State, ReleaseError]:
        saved.append(s)
        return Ok(s)

    def step_a(s: _State) -> Result[StepOutcome[_State], ReleaseError]:
        return Ok(advance(replace(s, step="b", counter=s.counter + 1)))

    def step_b(s: _State) -> Result[StepOutcome[_State], ReleaseError]:
        return Ok(FINISH)

    result = run_state_machine(
        initial_state=_State(step="a", counter=0),
        get_step=lambda s: s.step,
        handlers={"a": step_a, "b": step_b},
        save_state=save_state,
    )

    assert isinstance(result, Ok)
    assert saved == [_State(step="b", counter=1)]


def test_run_state_machine_unknown_step_fails() -> None:
    result = run_state_machine(
        initial_state=_State(step="missing", counter=0),
        get_step=lambda s: s.step,
        handlers={},
        save_state=lambda s: Ok(s),
    )

    assert isinstance(result, Err)
    assert result.error.kind == "invalid_input"


def test_run_state_machine_propagates_handler_error() -> None:
    def bad_step(_: _State) -> Result[StepOutcome[_State], ReleaseError]:
        return Err(ReleaseError(kind="invalid_input", message="boom"))

    result = run_state_machine(
        initial_state=_State(step="a", counter=0),
        get_step=lambda s: s.step,
        handlers={"a": bad_step},
        save_state=lambda s: Ok(s),
    )

    assert isinstance(result, Err)
