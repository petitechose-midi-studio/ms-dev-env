from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import TypeVar

from ms.core.result import Err, Ok, Result
from ms.services.release.errors import ReleaseError

S = TypeVar("S")


@dataclass(frozen=True, slots=True)
class StepAdvance[S]:
    session: S


@dataclass(frozen=True, slots=True)
class StepFinish:
    pass


StepOutcome = StepAdvance[S] | StepFinish
StepHandler = Callable[[S], Result[StepOutcome[S], ReleaseError]]
SaveState = Callable[[S], Result[S, ReleaseError]]
GetStep = Callable[[S], str]


FINISH = StepFinish()


def advance[S](session: S) -> StepAdvance[S]:
    return StepAdvance(session=session)


def run_state_machine(
    *,
    initial_state: S,
    get_step: GetStep[S],
    handlers: Mapping[str, StepHandler[S]],
    save_state: SaveState[S],
) -> Result[None, ReleaseError]:
    current = initial_state

    while True:
        step = get_step(current)
        handler = handlers.get(step)
        if handler is None:
            return Err(
                ReleaseError(
                    kind="invalid_input",
                    message=f"unknown release wizard step: {step}",
                )
            )

        outcome = handler(current)
        if isinstance(outcome, Err):
            return outcome

        if isinstance(outcome.value, StepFinish):
            return Ok(None)

        current = outcome.value.session
        saved = save_state(current)
        if isinstance(saved, Err):
            return saved
        current = saved.value
