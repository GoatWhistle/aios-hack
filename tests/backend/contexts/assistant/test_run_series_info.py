from backend.contexts.assistant.application.run_series_info import run_series_info
from backend.contexts.assistant.domain.guard import guard_chart_availability, guard_context_references


def test_empty_or_nonfinite_series_does_not_claim_available_chart() -> None:
    for rows in ([], [{"step": 0, "input_rate": None}], [{"step": 0, "input_rate": float("nan")}], [{"step": True, "input_rate": 35.0}]):
        info = run_series_info({"rows": rows})
        assert info["available"] is False
        assert info["has_multiple_steps"] is False


def test_single_recorded_step_is_available_without_claiming_multiple_steps() -> None:
    info = run_series_info({"rows": [{"step": 0, "date": "2007-01-01", "input_rate": 35.0}]})
    assert info["available"] is True
    assert info["has_multiple_steps"] is False
    assert info["from_date"] == info["to_date"] == "2007-01-01"
    text = "Записана только одна точка шага 0."
    assert guard_chart_availability(text, [{"run_series_info": info}], "ru").text == text


def test_absent_chart_metadata_does_not_invent_an_available_chart() -> None:
    text = "Временной ряд не записан отдельно."
    assert guard_chart_availability(text, [{"run_series_info": {"available": False}}], "ru").text == text


def test_chart_metadata_date_range_is_grounded_for_prose() -> None:
    text = "График от 2007-01-01 до 2025-09-01."
    evidence = [{"date": "2007-01-01", "run_series_info": {"from_date": "2007-01-01", "to_date": "2025-09-01"}}]
    result = guard_context_references(text, evidence, "ru")
    assert result.ok and result.text == text


def test_multistep_chart_does_not_rewrite_single_point_rule_observation() -> None:
    text = "The rule was evaluated at only one point."
    evidence = [{"run_series_info": {"available": True, "has_multiple_steps": True}}]
    result = guard_chart_availability(text, evidence, "en")
    assert result.ok and result.text == text
