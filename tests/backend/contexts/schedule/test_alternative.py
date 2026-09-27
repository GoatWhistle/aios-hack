from dataclasses import replace

import pytest

from backend.contexts.schedule.domain.alternative import set_producer_liquid_target
from backend.contexts.schedule.domain.schedule import (
    Availability,
    ControlEvent,
    EventKind,
    OperatingStatus,
    Role,
    Schedule,
    ScheduleMeta,
    WellState,
)


def producer_schedule() -> Schedule:
    return Schedule(
        meta=ScheduleMeta(n_control_dates=4, n_intervals=3, wells=("13",)),
        initial_state={
            "13": WellState(
                availability=Availability.AVAILABLE,
                role=Role.PROD,
                operating_status=OperatingStatus.OPEN,
                setpoint=100.0,
            )
        },
        fixed_deck_events=(),
        control_events=(
            ControlEvent(0, "13", EventKind.SET_LRAT, 100.0),
            ControlEvent(2, "13", EventKind.SET_LRAT, 120.0),
        ),
    )


def test_rate_alternative_changes_only_one_interval_and_reports_window() -> None:
    source = producer_schedule()

    result = set_producer_liquid_target(
        source, well="13", control_step=1, target_m3_per_day=80.0
    )

    assert result.action.as_dict() == {
        "kind": "producer-liquid-rate-target",
        "well": "13",
        "from_step": 1,
        "through_step": 1,
        "original_target_m3_per_day": 100.0,
        "alternative_target_m3_per_day": 80.0,
        "constraints_changed": False,
        "policy_reoptimized": False,
    }
    assert source.control_events[0].value == 100.0
    assert [(event.control_step, event.value) for event in result.schedule.control_events] == [
        (0, 100.0),
        (1, 80.0),
        (2, 120.0),
    ]
    assert result.schedule.meta.control_events_hash != source.meta.control_events_hash


def test_rate_alternative_preserves_open_action_at_the_selected_step() -> None:
    source = replace(
        producer_schedule(),
        control_events=producer_schedule().control_events
        + (ControlEvent(1, "13", EventKind.OPEN),),
    )

    result = set_producer_liquid_target(
        source, well="13", control_step=1, target_m3_per_day=80.0
    )

    assert [(event.kind, event.value) for event in result.schedule.control_events if event.control_step == 1] == [
        (EventKind.SET_LRAT, 80.0),
        (EventKind.OPEN, None),
    ]
    assert result.action.through_step == 1


@pytest.mark.parametrize("target", [0, -1, 500.01, float("nan"), float("inf"), True])
def test_rate_alternative_rejects_invalid_target(target: object) -> None:
    with pytest.raises(ValueError, match="target"):
        set_producer_liquid_target(
            producer_schedule(),
            well="13",
            control_step=1,
            target_m3_per_day=target,  # type: ignore[arg-type]
        )


def test_rate_alternative_rejects_unchanged_target_and_unknown_well() -> None:
    source = producer_schedule()
    with pytest.raises(ValueError, match="must differ"):
        set_producer_liquid_target(
            source, well="13", control_step=1, target_m3_per_day=100.0
        )
    with pytest.raises(ValueError, match="unknown well"):
        set_producer_liquid_target(
            source, well="404", control_step=1, target_m3_per_day=80.0
        )


def test_rate_alternative_rejects_non_producer_or_conflicting_control_action() -> None:
    source = producer_schedule()
    injection = replace(
        source,
        initial_state={
            "13": WellState(
                availability=Availability.AVAILABLE,
                role=Role.INJ,
                operating_status=OperatingStatus.OPEN,
                setpoint=100.0,
            )
        },
        control_events=(),
    )
    with pytest.raises(ValueError, match="not a commissioned producer"):
        set_producer_liquid_target(
            injection, well="13", control_step=0, target_m3_per_day=80.0
        )

    conflicting = replace(
        source,
        control_events=source.control_events
        + (ControlEvent(1, "13", EventKind.SHUT),),
    )
    with pytest.raises(ValueError, match="conflicting control action"):
        set_producer_liquid_target(
            conflicting, well="13", control_step=1, target_m3_per_day=80.0
        )


@pytest.mark.parametrize("control_step", [-1, 3, True])
def test_rate_alternative_rejects_invalid_step(control_step: object) -> None:
    with pytest.raises(ValueError, match="control_step"):
        set_producer_liquid_target(
            producer_schedule(),
            well="13",
            control_step=control_step,  # type: ignore[arg-type]
            target_m3_per_day=80.0,
        )
