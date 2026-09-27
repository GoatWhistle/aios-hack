from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from backend.contexts.assistant.application.tools import run_proposals
from backend.contexts.assistant.application.orchestrator_compose import _model_payload
from backend.contexts.assistant.application.tools.context import ConsoleContext, ToolContext
from backend.contexts.assistant.infrastructure.artifacts import ArtifactStore


def test_web_run_service_can_be_imported_before_assistant_tools() -> None:
    completed = subprocess.run(
        [sys.executable, "-c", "from backend.contexts.runs.application.web_runs import WebRuns; "
         "from backend.contexts.assistant.application.tools import run_tool; "
         "assert WebRuns and run_tool"],
        capture_output=True, text=True, check=False,
    )
    assert completed.returncode == 0, completed.stderr


def test_case_proposal_previews_saved_base_and_never_starts(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, store: ArtifactStore
) -> None:
    source = {"injection_limits": {"2007": 30000}}
    (tmp_path / "competition-constraints.json").write_text(json.dumps(source))
    monkeypatch.setattr(run_proposals.cases, "_config_root", lambda: tmp_path)
    calls: list[dict] = []

    def draft(payload: dict) -> dict:
        calls.append(payload)
        return {
            "operation": "set_annual_rate_limit", "section": "injection_limits",
            "year": 2007, "before": 30000, "after": 12000,
            "unit": "m3/day", "constraints": {"injection_limits": {"2007": 12000}},
        }

    monkeypatch.setattr(run_proposals, "_runs", lambda: SimpleNamespace(draft=draft))
    request = "Установи лимит закачки 12000 м3/сут в 2007 году"
    card = run_proposals.draft_case(
        ToolContext(store=store, console=ConsoleContext(scenario="base", lang="ru")),
        {"request": request},
    )

    assert calls == [{"request": request, "scenario": "base", "constraints": source}]
    assert card.type == "case-proposal"
    assert card.payload["base_constraints"] == source
    assert card.payload["requires_confirmation"] is True
    assert len(card.payload["request_id"]) == 32
    compact = _model_payload(card)
    assert "base_constraints" not in compact
    assert "constraints" not in compact
    assert "request_id" not in compact
    assert compact["after"] == 12000
    assert compact["proposed_rate"] == {"metric": "injection", "value": 12000, "unit": "m3/day"}


def test_alternative_proposal_uses_selected_context_without_starting(
    monkeypatch: pytest.MonkeyPatch, store: ArtifactStore
) -> None:
    calls: list[dict] = []

    def preview(payload: dict) -> dict:
        calls.append(payload)
        return {"source_run_id": payload["source_run_id"], "action": {
            "well": payload["well"], "from_step": payload["control_step"],
            "through_step": payload["control_step"],
            "original_target_m3_per_day": 40,
            "alternative_target_m3_per_day": payload["target_m3_per_day"],
        }}

    monkeypatch.setattr(run_proposals, "_runs", lambda: SimpleNamespace(draft_alternative=preview))
    card = run_proposals.draft_alternative(
        ToolContext(store=store, console=ConsoleContext(
            run_id="verified-1", selected_well="13", step=4, lang="en"
        )),
        {"target_m3_per_day": 50},
    )

    assert calls == [{
        "source_run_id": "verified-1", "well": "13", "control_step": 4,
        "target_m3_per_day": 50,
    }]
    assert card.type == "alternative-proposal"
    assert card.payload["requires_confirmation"] is True
