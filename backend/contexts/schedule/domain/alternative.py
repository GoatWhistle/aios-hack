"""Bounded fixed-action alternatives for an existing production schedule."""

from __future__ import annotations

import math
from dataclasses import dataclass, replace

from backend.contexts.schedule.domain.canonical import canonicalize
from backend.contexts.schedule.domain.schedule import (
    Availability,
    ControlEvent,
    EventKind,
    MAX_LRAT_M3_PER_DAY,
    OperatingStatus,
    Role,
    Schedule,
)
from backend.contexts.schedule.domain.validation.interpreter import (
    _target_at,
    _target_timeline,
)


@dataclass(frozen=True, slots=True)
class ProducerRateAlternative:
    """One explicit liquid-rate target change, with its actual persistence window."""

    well: str
    from_step: int
    through_step: int
    original_target_m3_per_day: float
    alternative_target_m3_per_day: float

    def as_dict(self) -> dict[str, object]:
        return {
            "kind": "producer-liquid-rate-target",
            "well": self.well,
            "from_step": self.from_step,
            "through_step": self.through_step,
            "original_target_m3_per_day": self.original_target_m3_per_day,
            "alternative_target_m3_per_day": self.alternative_target_m3_per_day,
            "constraints_changed": False,
            "policy_reoptimized": False,
        }


@dataclass(frozen=True, slots=True)
class AlternativeSchedule:
    schedule: Schedule
    action: ProducerRateAlternative


def set_producer_liquid_target(
    schedule: Schedule,
    *,
    well: str,
    control_step: int,
    target_m3_per_day: float,
) -> AlternativeSchedule:
    """Change one producer's LRAT at a step without modifying case constraints.

    The new target remains active until the next recorded LRAT command for that
    well. This function only constructs a schedule; the caller must submit it to
    the normal OPM and validation workflow before reporting any result.
    """
    if not isinstance(well, str) or well not in schedule.initial_state:
        raise ValueError(f"unknown well {well!r} in the source schedule")
    if type(control_step) is not int or not 0 <= control_step < schedule.meta.n_intervals:
        raise ValueError(
            f"control_step must be in 0..{schedule.meta.n_intervals - 1}"
        )
    if (
        isinstance(target_m3_per_day, bool)
        or not isinstance(target_m3_per_day, (int, float))
        or not math.isfinite(target_m3_per_day)
        or not 0 < target_m3_per_day <= MAX_LRAT_M3_PER_DAY
    ):
        raise ValueError(
            f"producer liquid target must be greater than 0 and at most "
            f"{MAX_LRAT_M3_PER_DAY} m3/day"
        )

    at_step = [
        event
        for event in schedule.control_events
        if event.control_step == control_step and event.well == well
    ]
    conflicting = [
        event for event in at_step
        if event.kind not in {EventKind.SET_LRAT, EventKind.OPEN}
    ]
    if conflicting or sum(event.kind is EventKind.SET_LRAT for event in at_step) > 1:
        raise ValueError(
            "this step has a conflicting control action for the well; the bounded "
            "LRAT alternative cannot safely replace it"
        )

    target = _target_at(_target_timeline(schedule)[well], control_step)
    if not target.commissioned or target.role is not Role.PROD:
        raise ValueError(f"well {well!r} is not a commissioned producer at this step")
    if target.operating_status is not OperatingStatus.OPEN or not target.setpoint_known:
        raise ValueError(f"well {well!r} has no known open producer target at this step")
    if math.isclose(target.setpoint, float(target_m3_per_day), rel_tol=0.0, abs_tol=1e-9):
        raise ValueError("the alternative target must differ from the recorded target")

    events = [
        event
        for event in schedule.control_events
        if not (
            event.control_step == control_step
            and event.well == well
            and event.kind is EventKind.SET_LRAT
        )
    ]
    events.append(
        ControlEvent(
            control_step=control_step,
            well=well,
            kind=EventKind.SET_LRAT,
            value=float(target_m3_per_day),
        )
    )
    later_actions = [
        event.control_step
        for event in schedule.control_events
        if event.well == well
        and event.control_step > control_step
        and event.kind is not EventKind.OPEN
    ]
    through_step = min(later_actions) - 1 if later_actions else schedule.meta.n_intervals - 1
    action = ProducerRateAlternative(
        well=well,
        from_step=control_step,
        through_step=through_step,
        original_target_m3_per_day=float(target.setpoint),
        alternative_target_m3_per_day=float(target_m3_per_day),
    )
    return AlternativeSchedule(
        schedule=canonicalize(replace(schedule, control_events=tuple(events))),
        action=action,
    )


__all__ = [
    "AlternativeSchedule",
    "ProducerRateAlternative",
    "set_producer_liquid_target",
]
