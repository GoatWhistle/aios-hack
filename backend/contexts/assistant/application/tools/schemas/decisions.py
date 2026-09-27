from __future__ import annotations

from backend.contexts.assistant.application.tools.schemas.base import (
    ToolDefinition,
    obj,
)

ALTERNATIVE_STATUSES: tuple[str, ...] = (
    "recorded-comparison",
    "state-comparison-only",
    "separate-calculation-required",
)


DECISION_TOOLS: tuple[ToolDefinition, ...] = (
    ToolDefinition(
        name="explain_decision",
        description=(
            "Why the system took a decision for a well at a step: the rule that "
            "fired, its actual inputs and the decision. If well or step is omitted, "
            "use the selected well and step/date from console context when available."
        ),
        schema=obj(
            {"well": {"type": "string"}, "step": {"type": "integer"}},
            (),
        ),
        card_type="rule",
    ),
    ToolDefinition(
        name="decision_journal",
        description=(
            "The journal facts recorded for a well at a control step: every rule "
            "that fired, its recorded inputs, proposed actions and final scheduled "
            "commands. Supply run_id to read the indexed generation journal for a "
            "specific run, defaulting to the run_id selected in console context; a registered "
            "submitted plan with no source journal returns an explicit unavailable-evidence refusal. "
            "Without either run_id, reads the active showcase trace. Omitted well "
            "and step use the selected well and step/date from console context."
        ),
        schema=obj(
            {"well": {"type": "string"}, "step": {"type": "integer"}, "run_id": {"type": "string"}},
            (),
        ),
        card_type="rule",
    ),
    ToolDefinition(
        name="rule_impact",
        description=(
            "The contribution of rules R0 to R7 to NPV by ablation: delta, share "
            "and whether the contribution was measured at all."
        ),
        schema=obj({"rule": {"type": "string"}}),
        card_type="rule",
    ),
    ToolDefinition(
        name="compare_scenarios",
        description=(
            "Comparison of two scenarios: NPV, constraints, status and the wells "
            "with the largest difference."
        ),
        schema=obj({"a": {"type": "string"}, "b": {"type": "string"}}, ("a", "b")),
        card_type="compare",
    ),
)
