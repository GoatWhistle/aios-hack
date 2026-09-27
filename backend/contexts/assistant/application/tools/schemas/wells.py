from __future__ import annotations

from backend.contexts.assistant.application.tools.schemas.base import (
    SERIES_METRICS,
    ToolDefinition,
    obj,
)
from backend.contexts.schedule.domain.schedule import N_INTERVALS

MAX_SERIES_STEP = N_INTERVALS


WELL_TOOLS: tuple[ToolDefinition, ...] = (
    ToolDefinition(
        name="well_snapshot",
        description=(
            "Snapshot of one well at a control step: role, status, liquid rate, "
            "injection, water cut, bottomhole pressure, NPV and a rate sparkline."
        ),
        schema=obj(
            {
                "well": {"type": "string", "description": "well identifier"},
                "step": {
                    "type": "integer",
                    "description": "control step 0-224; taken from the console context by default",
                },
            },
            ("well",),
        ),
        card_type="well",
    ),
    ToolDefinition(
        name="well_series",
        description=(
            "A series of one value for a well over a step interval: liquid rate, "
            "injection, water cut or bottomhole pressure."
        ),
        schema=obj(
            {
                "well": {"type": "string"},
                "metric": {"type": "string", "enum": list(SERIES_METRICS)},
                "from_step": {"type": "integer", "minimum": 0, "maximum": MAX_SERIES_STEP},
                "to_step": {"type": "integer", "minimum": 0, "maximum": MAX_SERIES_STEP},
                "window": {
                    "type": "array",
                    "minItems": 2,
                    "maxItems": 2,
                    "items": {"type": "integer", "minimum": 0, "maximum": MAX_SERIES_STEP},
                    "description": "highlight interval [from, to] inside the series",
                },
            },
            ("well", "metric"),
        ),
        card_type="series",
    ),
    ToolDefinition(
        name="compare_wells",
        description=(
            "Compare two wells at one control step using the recorded state: role, "
            "availability, operating status, liquid and injection rates, water cut, "
            "pressure, setpoint and whole-horizon NPV. Reports measured direct "
            "connectivity and whether decision evidence exists for each well. It "
            "does not claim a recorded pairwise preference or causal effect."
        ),
        schema=obj(
            {
                "a": {"type": "string", "description": "first well identifier"},
                "b": {"type": "string", "description": "second well identifier"},
                "step": {"type": "integer", "description": "control step; defaults to console context"},
                "run_id": {"type": "string", "description": "optional run for recorded decision evidence"},
            },
            ("a", "b"),
        ),
        card_type="well-comparison",
    ),
)
