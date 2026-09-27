from __future__ import annotations

import math

import pytest

from backend.contexts.assistant.application.tools import HANDLERS, error_card, run_tool, tool_specs
from backend.contexts.assistant.application.tools.context import ConsoleContext, ToolContext, ToolFailure
from backend.contexts.assistant.application.tools.registry import (
    BY_NAME,
    ToolInputError,
    validate_arguments,
)
from backend.contexts.assistant.domain.guard import TOOL_SUBJECT_PATTERNS
from backend.contexts.assistant.infrastructure.artifacts import ArtifactStore


def test_every_registered_tool_has_one_executable_handler() -> None:
    assert set(HANDLERS) == set(BY_NAME)
    assert len(tool_specs()) == len(BY_NAME) == 27


def test_tool_failure_guard_has_subject_patterns_for_every_registered_tool() -> None:
    assert set(TOOL_SUBJECT_PATTERNS) == set(BY_NAME)


def test_every_tool_error_card_preserves_reason_and_offers_next_step() -> None:
    for tool in BY_NAME:
        card = error_card(tool, "the requested data is unavailable", "en")
        assert card.payload["message"] == "the requested data is unavailable"
        assert card.payload["next_step"]
        assert card.payload["expected_card"] == BY_NAME[tool].card_type
        assert card.title != f"Tool failed: {tool}"


def test_no_findings_error_suggests_a_diagnostic_next_step() -> None:
    card = error_card("find_patterns", "the detectors found no anomaly", "en")

    assert card.payload["message"] == "the detectors found no anomaly"
    assert card.payload["next_step"] == (
        "Widen the step interval or choose another supported diagnostic pattern."
    )


@pytest.mark.parametrize("bad_step", [True, 1.5, math.inf, math.nan])
def test_integer_tool_arguments_reject_booleans_fractions_and_non_finite_values(
    bad_step: object,
) -> None:
    with pytest.raises(ToolInputError, match="integer"):
        validate_arguments("well_snapshot", {"well": "W1", "step": bad_step})


@pytest.mark.parametrize("bad_limit", [True, math.inf, math.nan])
def test_numeric_tool_arguments_reject_booleans_and_non_finite_values(
    bad_limit: object,
) -> None:
    with pytest.raises(ToolInputError):
        validate_arguments("connectivity", {"well": "W1", "min_weight": bad_limit})


@pytest.mark.parametrize(
    ("tool", "arguments"),
    [
        ("rank_wells", {"by": "npv", "limit": 11}),
        ("well_series", {"well": "W1", "metric": "bhp", "to_step": 225}),
    ],
)
def test_rank_and_series_limits_are_enforced_by_the_public_schema(
    tool: str, arguments: dict[str, object]
) -> None:
    with pytest.raises(ToolInputError, match="above the maximum"):
        validate_arguments(tool, arguments)


def test_tool_dispatch_rejects_unknown_inputs_before_handler_execution(
    store: ArtifactStore,
) -> None:
    context = ToolContext(store=store, console=ConsoleContext(scenario="base", step=0))
    with pytest.raises((ToolInputError, ToolFailure), match="unknown|does not accept"):
        run_tool("well_snapshot", context, {"well": "W1", "invented": 1})
