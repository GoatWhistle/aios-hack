from __future__ import annotations

from backend.contexts.assistant.application.tools.schemas.base import (
    ToolDefinition,
    obj,
)


RUN_TOOLS: tuple[ToolDefinition, ...] = (
    ToolDefinition(
        name="draft_case",
        description=(
            "Prepare, without launching, a new calculation case from a user's explicit "
            "well outage with dates or annual injection/liquid limit. The active "
            "scenario and saved competition constraints are used. Returns a "
            "reviewable proposal requiring a person's confirmation. Never claim "
            "that the calculation started after calling this tool."
        ),
        schema=obj({"request": {"type": "string", "description": "The user's exact case change request"}}, ("request",)),
        card_type="case-proposal",
    ),
    ToolDefinition(
        name="draft_alternative",
        description=(
            "Prepare, without launching, one SET_LRAT producer target change against "
            "a saved sound OPM source run. Use the selected run, well and step "
            "unless the user names them. Requires an explicit target in m3/day. "
            "The preview shows the action span and source hashes; the person "
            "must confirm before any new OPM calculation starts."
        ),
        schema=obj(
            {
                "source_run_id": {"type": "string", "description": "Saved sound OPM run ID; selected run by default"},
                "well": {"type": "string", "description": "Producer well; selected well by default"},
                "control_step": {"type": "integer", "minimum": 0, "description": "First changed control step; selected step by default"},
                "target_m3_per_day": {"type": "number", "minimum": 0.01, "maximum": 500, "description": "Proposed SET_LRAT liquid target in m3/day"},
            },
            ("target_m3_per_day",),
        ),
        card_type="alternative-proposal",
    ),
    ToolDefinition(
        name="run_status",
        description=(
            "The recorded state of a calculation run read from its manifest: "
            "status, predicted and verified NPV, soundness, dynamic violations "
            "and the search strategy. Includes deterministic acceptance with "
            "surrogate and OPM NPV sources kept separate; missing checks stay "
            "unknown. Answers with the numbers the manifest "
            "holds and reports a field the manifest never recorded as not "
            "recorded, never as zero. Without run_id the latest run is read."
        ),
        schema=obj(
            {
                "run_id": {
                    "type": "string",
                    "description": "run directory name; the latest run by default",
                }
            }
        ),
        card_type="run-status",
    ),
    ToolDefinition(
        name="submission_summary",
        description=(
            "The submission package of a run: claimed NPV in roubles, the "
            "canonical schedule and content hashes, the deck, constraints, "
            "economics and methodology hashes, the OPM image and the git "
            "commit, all read from submission/claimed_npv.json, plus whether "
            "the package files are in place. Says plainly that no package was "
            "assembled when the run has none."
        ),
        schema=obj(
            {
                "run_id": {
                    "type": "string",
                    "description": "run directory name; the latest run by default",
                }
            }
        ),
        card_type="submission",
    ),
)
