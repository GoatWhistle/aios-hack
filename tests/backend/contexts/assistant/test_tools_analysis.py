from __future__ import annotations

from types import SimpleNamespace

import pytest

from backend.contexts.assistant.infrastructure.artifacts import ArtifactStore
from backend.contexts.assistant.domain.cancellation import CancellationToken
from backend.contexts.assistant.application.tools import run_tool
from backend.contexts.assistant.application.tools.context import (
    ConsoleContext,
    ToolContext,
    ToolFailure,
)
from backend.contexts.assistant.application.tools import system as system_tools
from backend.contexts.assistant.application.tools.patterns import find_patterns
from backend.contexts.assistant.application.tools.rules import _trace_entries

WORST_NPV = ["76", "6", "65", "13", "8", "17", "83", "102", "53", "25"]


def make(store: ArtifactStore, **console: object) -> ToolContext:
    return ToolContext(store=store, console=ConsoleContext(**console))


def test_status_diagnostics_distinguish_no_findings_from_unavailable_data(
    monkeypatch: pytest.MonkeyPatch, store: ArtifactStore
) -> None:
    context = make(store, scenario="base", step=96)

    def no_findings(*_args: object, **_kwargs: object) -> None:
        raise ToolFailure("the detectors found no anomaly for well 13")

    monkeypatch.setattr(system_tools, "find_patterns", no_findings)
    empty = system_tools._alerts(context)
    assert empty == {"recorded": True, "reason": None, "rows": []}

    def unavailable(*_args: object, **_kwargs: object) -> None:
        raise ToolFailure("the selected scenario data is unavailable")

    monkeypatch.setattr(system_tools, "find_patterns", unavailable)
    missing = system_tools._alerts(context)
    assert missing["recorded"] is False
    assert "data is unavailable" in missing["reason"]


def test_fieldwide_pattern_scan_stops_when_its_request_is_cancelled(
    store: ArtifactStore,
) -> None:
    cancellation = CancellationToken()
    cancellation.cancel()
    context = ToolContext(
        store=store,
        console=ConsoleContext(scenario="base"),
        cancellation=cancellation,
    )
    with pytest.raises(ToolFailure, match="cancelled"):
        find_patterns(context, {"limit": 10})


def test_trace_materialization_checks_deadline_during_large_scan() -> None:
    trace = {
        "13": {
            "0": [
                {"rule": "R0", "inputs": {}, "decision": "KEEP"}
                for _ in range(300)
            ]
        }
    }

    class Deadline:
        checks = 0

        def check_cancelled(self) -> None:
            self.checks += 1
            if self.checks == 2:
                raise TimeoutError("deadline reached")

    context = Deadline()
    with pytest.raises(TimeoutError, match="deadline reached"):
        _trace_entries(SimpleNamespace(trace=trace), context)
    assert context.checks == 2


def test_status_exposes_latest_run_violations_with_their_own_run_id(
    monkeypatch: pytest.MonkeyPatch, store: ArtifactStore
) -> None:
    from backend.contexts.assistant.application.tools.context import Card

    rows = [{"kind": f"K{index}", "control_step": index, "well": "W1"} for index in range(5)]
    status = Card(type="run-status", title="status", payload={
        "run_id": "run-latest",
        "violation_locations": {"recorded": True, "reason": None, "rows": rows},
    }, provenance="run-manifest")
    monkeypatch.setattr(system_tools, "run_status", lambda *_args, **_kwargs: status)

    result = system_tools._latest_violations(make(store))

    assert result["run_id"] == "run-latest"
    assert result["recorded"] is True
    assert len(result["rows"]) == 3


def test_rank_wells_worst_by_npv(store: ArtifactStore) -> None:
    card = run_tool("rank_wells", make(store, step=96), {"by": "npv", "order": "asc"})
    assert card.type == "well-list"
    assert [row["well"] for row in card.payload["rows"]] == WORST_NPV
    assert card.payload["rows"][0]["value"] == pytest.approx(-31500502.0, abs=1.0)
    assert card.payload["unit"] == "RUB"
    assert card.payload["period"] == "whole_horizon"
    assert card.payload["step"] is None
    assert card.payload["date"] is None
    assert card.payload["total_count"] >= len(card.payload["rows"])
    assert card.provenance == "model-z-base-run"


def test_rank_wells_respects_limit(store: ArtifactStore) -> None:
    card = run_tool(
        "rank_wells",
        make(store, step=96),
        {"by": "watercut", "order": "desc", "limit": 3},
    )
    assert len(card.payload["rows"]) == 3
    values = [row["value"] for row in card.payload["rows"]]
    assert values == sorted(values, reverse=True)
    assert card.payload["period"] == "control_step"
    assert card.payload["step"] == 96
    assert card.payload["date"] == make(store, step=96).index().dates[96]
    assert card.payload["total_count"] > len(card.payload["rows"])


def test_rank_wells_action_points_at_money(store: ArtifactStore) -> None:
    card = run_tool("rank_wells", make(store), {"by": "npv", "order": "asc"})
    assert card.action["workspace"] == "money"
    assert card.action["view"] == "rank"
    assert card.action["well"] == "76"


def test_rule_impact_marks_unmeasured(store: ArtifactStore) -> None:
    card = run_tool("rule_impact", make(store), {})
    assert card.type == "rule"
    by_rule = {row["rule"]: row for row in card.payload["rules"]}
    for row in by_rule.values():
        assert row["delta"] is None
        assert row["measured"] is False
    assert by_rule["R7"]["enabled"] is False
    assert by_rule["R7"]["disabled_reason"] == "UPLIFT_NOT_MEASURED"
    assert card.provenance == "ablation-not-run"


def test_rule_impact_statement_comes_from_policy(store: ArtifactStore) -> None:
    card = run_tool("rule_impact", make(store), {"rule": "R0"})
    assert len(card.payload["rules"]) == 1
    assert card.payload["rules"][0]["statement"]


def test_rule_impact_unknown_rule_fails(store: ArtifactStore) -> None:
    with pytest.raises(ToolFailure):
        run_tool("rule_impact", make(store), {"rule": "R99"})


def test_explain_decision_on_scenario_with_trace(store: ArtifactStore) -> None:
    context = make(store, scenario="whatif-injection-cut")
    card = run_tool("explain_decision", context, {"well": "13", "step": 10})
    assert card.type == "rule"
    assert card.payload["rule"] == "R1"
    assert card.payload["inputs"] == {"liquid_rate": 112.9, "watercut": 0.614}
    assert card.payload["decision"] == "SET_LRAT 112.9"
    assert card.payload["statement"]
    assert card.action["workspace"] == "decisions"
    assert card.action["view"] == "rules"


def test_explain_decision_without_trace_refuses(store: ArtifactStore) -> None:
    with pytest.raises(ToolFailure) as error:
        run_tool("explain_decision", make(store), {"well": "13", "step": 10})
    assert "no Trace records" in str(error.value)


def test_explain_decision_step_without_firing_refuses(store: ArtifactStore) -> None:
    context = make(store, scenario="whatif-injection-cut")
    with pytest.raises(ToolFailure) as error:
        run_tool("explain_decision", context, {"well": "13", "step": 11})
    assert "no rule fired" in str(error.value)


def test_compare_scenarios_real_numbers(store: ArtifactStore) -> None:
    card = run_tool(
        "compare_scenarios", make(store), {"a": "base", "b": "whatif-injection-cut"}
    )
    assert card.type == "compare"
    assert card.payload["a"]["id"] == "base"
    assert card.payload["b"]["id"] == "whatif-injection-cut"
    assert card.payload["a"]["npv"] == pytest.approx(11873122324.910866)
    assert len(card.payload["top_diff_wells"]) == 10
    deltas = [abs(row["delta"]) for row in card.payload["top_diff_wells"]]
    assert deltas == sorted(deltas, reverse=True)
    assert card.action["scenario"] == "whatif-injection-cut"


def test_compare_scenarios_with_itself_refuses(store: ArtifactStore) -> None:
    with pytest.raises(ToolFailure) as error:
        run_tool("compare_scenarios", make(store), {"a": "base", "b": "base"})
    assert "compared with itself" in str(error.value)


def test_compare_scenarios_unknown_refuses(store: ArtifactStore) -> None:
    with pytest.raises(ToolFailure):
        run_tool("compare_scenarios", make(store), {"a": "base", "b": "nope"})


def test_connectivity_reads_measured_graph(store: ArtifactStore) -> None:
    card = run_tool("connectivity", make(store), {"well": "1", "limit": 5})
    assert card.type == "field-map"
    assert card.payload["focus"] == ["1"]
    assert len(card.payload["edges"]) == 5
    weights = [row["weight"] for row in card.payload["edges"]]
    assert weights == sorted(weights, reverse=True)
    assert card.payload["lag_months"] == 0
    assert card.action["workspace"] == "field"
    assert card.action["well"] == "1"


def test_connectivity_threshold_can_exclude_everything(store: ArtifactStore) -> None:
    with pytest.raises(ToolFailure) as error:
        run_tool("connectivity", make(store), {"well": "1", "min_weight": 5.0})
    assert "strongest neighbour" in str(error.value)


def test_rank_wells_refuses_when_metric_absent_at_step(
    store: ArtifactStore,
) -> None:
    with pytest.raises(ToolFailure) as error:
        run_tool(
            "rank_wells", make(store, step=224), {"by": "watercut", "order": "desc"}
        )
    assert "has no measurement at step 224" in str(error.value)


def test_connectivity_unknown_well_refuses(store: ArtifactStore) -> None:
    with pytest.raises(ToolFailure):
        run_tool("connectivity", make(store), {"well": "45"})


def test_find_patterns_uses_diagnostics_catalogue(store: ArtifactStore) -> None:
    card = run_tool("find_patterns", make(store), {"limit": 5})
    assert card.type == "pattern"
    assert card.payload["total"] >= 1
    identifiers = {row["pattern_id"] for row in card.payload["patterns"]}
    assert identifiers <= {
        "pressure_drop_at_high_rates",
        "wct_rise_without_oil",
        "injection_without_response",
    }
    assert all(row["inputs"] for row in card.payload["patterns"])
    for row in card.payload["patterns"]:
        if row["step"] is not None:
            assert row["date"] == store.scenario("base").dates[row["step"]]
        if row["window"] is not None:
            start, end = row["window"]
            assert row["window_dates"] == [
                store.scenario("base").dates[start],
                store.scenario("base").dates[end],
            ]


def test_find_patterns_unknown_pattern_refuses(store: ArtifactStore) -> None:
    with pytest.raises(ToolFailure) as error:
        run_tool("find_patterns", make(store), {"pattern": "aliens"})
    assert "cannot be detected" in str(error.value)
