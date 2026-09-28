import json
from pathlib import Path

import pytest

from backend.contexts.assistant.application.journal_explanation import journal_explanation


def _payload() -> dict:
    return json.loads((Path(__file__).parent / "fixtures/journal_s10.json").read_text())


def test_real_journal_explanation_keeps_input_proposals_and_final_schedule_distinct() -> None:
    text = journal_explanation(_payload())
    assert "Скважина 62, шаг 0, дата 2007-01-01" in text
    assert "нагнетательная; открыта" in text
    assert "Исходная уставка: 35 м³/сут" in text
    assert "Исходная измеренная закачка: 35 м³/сут" in text
    assert "Лимит закачки фонда: 69.7653 м³/сут" in text
    assert "R1 (группа): цель 0 м³/сут" in text
    assert "R5 (группа): цель 2.04319 м³/сут" in text
    assert "коридор 0.9–1.15" in text
    assert "R5 (скважина): предложение исполнителя 2 м³/сут" in text
    assert "Итоговое расписание: `SET_RATE` 1 м³/сут; `OPEN`" in text
    assert "Отдельная причина" in text and "не записана" in text


@pytest.mark.parametrize("value", [None, "999999", True, float("nan"), float("inf")])
def test_missing_or_untyped_observation_is_explicitly_unknown(value: object) -> None:
    payload = _payload()
    payload["input_observation"]["setpoint_m3_per_day"] = value
    text = journal_explanation(payload)
    assert "Исходная уставка: не записано." in text
    assert "Исходная уставка: не записано м³/сут" not in text
    assert "999999" not in text


def test_absent_journal_fields_never_render_empty_measurements() -> None:
    text = journal_explanation({"decision_summary": {}, "record_status": "recorded"})
    assert "Исходная уставка: не записано." in text
    assert "Исходная измеренная закачка: не записано." in text
    assert "Предложения правил не записаны." in text
    assert "Итоговое расписание: не записано." in text
    assert "м³/сут" not in text


def test_non_journal_cards_have_no_trusted_explanation() -> None:
    assert journal_explanation({"run_id": "other-run", "rule": "R1"}) is None


def test_producer_explanation_uses_measured_liquid_rate_and_real_rate_event_unit() -> None:
    payload = _payload()
    payload["input_observation"].update(role="PROD", liquid_rate_m3_per_day=123.5, injection_rate_m3_per_day=0.0)
    payload["final_schedule_events"] = [{"kind": "SET_LRAT", "value": 120.0}]
    text = journal_explanation(payload)
    assert "Исходный измеренный дебит жидкости: 123.5 м³/сут" in text
    assert "Исходная измеренная закачка" not in text
    assert "`SET_LRAT` 120 м³/сут" in text
