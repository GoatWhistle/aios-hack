from __future__ import annotations

import pytest

from backend.contexts.assistant.domain.guard import (
    _METRIC_UNITS,
    _field_metric,
    _field_unit,
    TOOL_SUBJECT_PATTERNS,
    allowed_numbers,
    collect_numbers,
    guard_caption,
    guard_context_references,
    guard_decision_claims,
    guard_plan_status,
    guard_run_references,
    guard_tool_failure_claims,
    unsupported_numbers,
)
from backend.contexts.assistant.application.tools.labels import METRIC_UNITS
from backend.contexts.assistant.application.tools.ranking import RANK_METRICS
from backend.contexts.assistant.application.tools.wells import SERIES_METRICS

PAYLOADS = [
    {
        "npv": 1161713780.758579,
        "watercut": 0.96,
        "rows": [{"well": "13", "value_rub": -20491675.0}],
        "active_wells": 96,
    },
    {"total_npv_rub": 11873122324.910866, "share": 0.097844},
]


def test_guard_metric_contract_covers_all_field_series_and_ranking_metrics() -> None:
    assert set(SERIES_METRICS) | set(RANK_METRICS) <= set(METRIC_UNITS)
    for metric_id, unit_tag in METRIC_UNITS.items():
        guard_metric = _field_metric(metric_id)
        assert guard_metric is not None, metric_id
        assert _field_unit(unit_tag) == _METRIC_UNITS.get(guard_metric), metric_id


def test_number_from_tool_passes_verbatim() -> None:
    result = guard_caption("Вклад правила R0 — 1 161 713 781 руб.", PAYLOADS)
    assert result.ok is True
    assert result.dropped == ()
    assert "1 161 713 781" in result.text


def test_percent_form_of_a_fraction_passes() -> None:
    result = guard_caption("Обводнённость дошла до 96 %.", PAYLOADS)
    assert result.ok is True


def test_number_match_does_not_justify_a_claim_with_the_wrong_unit() -> None:
    result = guard_caption("Watercut was 96 rubles.", [{"watercut": 0.96}])

    assert result.ok is False
    assert result.dropped == ("96",)


def test_currency_unit_accepts_a_scaled_value_from_npv_evidence() -> None:
    result = guard_caption("Verified NPV was 11.9 billion rubles.", [{"verified_npv_rub": 11873122324.91}])

    assert result.ok is True


def test_rate_unit_matches_rate_evidence() -> None:
    result = guard_caption("Oil rate was 12.5 m3/day.", [{"oil_rate_m3_per_day": 12.5}])

    assert result.ok is True


@pytest.mark.parametrize(
    "claim",
    [
        "Oil production was 12.5 m3/day.",
        "Добыча нефти составила 12,5 м³/сут.",
    ],
)
def test_oil_production_alias_requires_oil_rate_evidence(claim: str) -> None:
    result = guard_caption(claim, [{"field_production_m3_per_day": 12.5}])

    assert result.ok is False
    assert result.dropped == ("12,5" if "," in claim else "12.5",)


@pytest.mark.parametrize(
    "claim",
    [
        "Oil production was 12.5 m3/day.",
        "Добыча нефти составила 12,5 м³/сут.",
    ],
)
def test_oil_production_alias_accepts_matching_oil_rate_evidence(claim: str) -> None:
    result = guard_caption(claim, [{"oil_rate_m3_per_day": 12.5}])

    assert result.ok is True


def test_explicit_rate_unit_tag_grounds_a_nested_measurement() -> None:
    result = guard_caption(
        "The recorded value was 12.5 m3/day.",
        [{"unit": "m3/day", "series": [{"value": 12.5}]}],
    )

    assert result.ok is True
    assert result.text == "The recorded value was 12.5 m3/day."


@pytest.mark.parametrize(
    ("unit", "claim"),
    [
        ("RUB/m3", "Unit price was 12 RUB/m3."),
        ("RUB/t", "Unit price was 12 RUB/t."),
        ("t/m3", "Density was 12 t/m3."),
        ("fraction", "The measured fraction was 0.5 fraction."),
        ("coefficient", "The coefficient was 0.5 coefficient."),
        ("wells", "There were 12 wells."),
        ("steps", "There were 12 steps."),
        ("records", "There were 12 records."),
        ("months", "The condition lasted 12 months."),
        ("years", "The condition lasted 12 years."),
    ],
)
def test_explicit_unit_tags_ground_nested_values(unit: str, claim: str) -> None:
    value = 0.5 if unit in {"fraction", "coefficient"} else 12
    result = guard_caption(claim, [{"unit": unit, "values": [value]}])

    assert result.ok is True


@pytest.mark.parametrize(
    ("claim", "evidence"),
    [
        ("Unit price was 12 RUB/m3.", {"unit": "m3", "values": [12]}),
        ("Density was 12 t/m3.", {"unit": "m3", "values": [12]}),
        ("There were 12 steps.", {"unit": "wells", "values": [12]}),
        ("There were 12 wells.", {"unit": "steps", "values": [12]}),
    ],
)
def test_unit_tags_do_not_borrow_matching_values_from_another_dimension(
    claim: str, evidence: dict[str, object]
) -> None:
    result = guard_caption(claim, [evidence])

    assert result.ok is False


def test_well_count_cannot_borrow_a_matching_rate_value() -> None:
    result = guard_caption("The scenario has 12 wells.", [{"oil_rate_m3_per_day": 12.0}])

    assert result.ok is False
    assert result.dropped == ("12",)


def test_russian_iteration_count_matches_only_count_evidence() -> None:
    result = guard_caption("Выполнено 224 итерации.", [{"iteration_count": 224}])

    assert result.ok is True


def test_well_count_matches_active_well_evidence() -> None:
    result = guard_caption("There are 96 active wells.", [{"active_wells": 96}])

    assert result.ok is True


def test_matching_rate_from_another_metric_does_not_support_the_claim() -> None:
    result = guard_caption(
        "Oil rate was 12.5 m3/day.",
        [{"oil_rate_m3_per_day": 19.0, "injection_rate_m3_per_day": 12.5}],
    )

    assert result.ok is False
    assert result.dropped == ("12.5",)


def test_pressure_claim_uses_bhp_evidence_not_matching_rate() -> None:
    result = guard_caption(
        "Bottomhole pressure was 12 bar.",
        [{"bhp_bar": 91.0, "liquid_rate_m3_per_day": 12.0}],
    )

    assert result.ok is False
    assert result.dropped == ("12",)


def test_pressure_claim_accepts_matching_bhp_value() -> None:
    result = guard_caption("Bottomhole pressure was 91 bar.", [{"bhp_bar": 91.0}])

    assert result.ok is True


def test_metric_context_does_not_leak_into_the_next_sentence() -> None:
    result = guard_caption(
        "Oil rate was 12.5 m3/day. API score was 0.5.",
        [{"oil_rate_m3_per_day": 12.5, "ood_score": 0.5}],
    )

    assert result.ok is True
    assert result.text == "Oil rate was 12.5 m3/day. API score was 0.5."


def test_setpoint_claim_does_not_borrow_matching_injection_rate() -> None:
    result = guard_caption(
        "Setpoint was 12 m3/day.",
        [{"setpoint_m3_per_day": 8.0, "injection_rate_m3_per_day": 12.0}],
    )

    assert result.ok is False
    assert result.dropped == ("12",)


def test_field_production_claim_uses_aggregate_production_value() -> None:
    result = guard_caption(
        "Field production was 12 m3/day.",
        [{"production": 14.0, "liquid_rate": 12.0}],
    )

    assert result.ok is False
    assert result.dropped == ("12",)


def test_field_production_claim_accepts_aggregate_production_value() -> None:
    result = guard_caption("Field production was 14 m3/day.", [{"production": 14.0}])

    assert result.ok is True


def test_series_metric_discriminator_grounds_nested_value() -> None:
    result = guard_caption(
        "Liquid rate was 12.5 m3/day.",
        [{"metric": "liquid_rate", "unit": "m3/day", "rows": [{"step": 0, "value": 12.5}]}],
    )

    assert result.ok is True


@pytest.mark.parametrize(
    ("claim", "evidence"),
    [
        ("Дебит закачки 12,5 м³/сут.", [{"metric": "injection_rate", "unit": "m3/day", "rows": [{"step": 0, "value": 12.5}]}]),
        ("Injection rate was 12.5 m3/day.", [{"metric": "injection_rate", "unit": "m3/day", "rows": [{"step": 0, "value": 12.5}]}]),
    ],
)
def test_injection_rate_claim_uses_well_rate_evidence(claim: str, evidence: list[dict]) -> None:
    result = guard_caption(claim, evidence)

    assert result.ok is True


@pytest.mark.parametrize("claim", ["Дебит закачки 12,5 м³/сут.", "Injection rate was 12.5 m3/day."])
def test_injection_rate_claim_does_not_borrow_field_injection(claim: str) -> None:
    result = guard_caption(claim, [{"metrics": [{"id": "injection", "value": 12.5, "unit": "m3/day"}]}])

    assert result.ok is False
    assert result.dropped


def test_series_metric_discriminator_does_not_borrow_another_metric() -> None:
    result = guard_caption(
        "Liquid rate was 12.5 m3/day.",
        [{"metric": "injection_rate", "unit": "m3/day", "rows": [{"step": 0, "value": 12.5}]}],
    )

    assert result.ok is False
    assert result.dropped == ("12.5",)


def test_field_metric_id_grounds_value_in_aggregate_metrics() -> None:
    result = guard_caption(
        "Field production was 12.5 m3/day.",
        [{"metrics": [{"id": "production", "value": 12.5, "unit": "m3/day"}]}],
    )

    assert result.ok is True


def test_field_metric_id_does_not_borrow_different_metric() -> None:
    result = guard_caption(
        "Field production was 12.5 m3/day.",
        [{"metrics": [{"id": "injection", "value": 12.5, "unit": "m3/day"}]}],
    )

    assert result.ok is False
    assert result.dropped == ("12.5",)


def test_compensation_claim_does_not_borrow_watercut_value() -> None:
    result = guard_caption(
        "Compensation was 75%.", [{"compensation": 0.5, "watercut": 0.75}]
    )

    assert result.ok is False
    assert result.dropped == ("75",)


def test_compensation_claim_accepts_its_own_fraction_as_percent() -> None:
    result = guard_caption("Compensation was 50%.", [{"compensation": 0.5}])

    assert result.ok is True


def test_active_well_claim_uses_active_well_count() -> None:
    result = guard_caption(
        "The active well stock is 96.", [{"active_wells": 94, "oil_rate": 96.0}]
    )

    assert result.ok is False
    assert result.dropped == ("96",)


def test_active_well_claim_accepts_its_recorded_count() -> None:
    result = guard_caption("The active well stock is 94.", [{"active_wells": 94}])

    assert result.ok is True


def test_metric_without_explicit_unit_still_requires_its_own_value() -> None:
    result = guard_caption(
        "Oil rate was 12.5.",
        [{"oil_rate_m3_per_day": 19.0, "injection_rate_m3_per_day": 12.5}],
    )

    assert result.ok is False
    assert result.dropped == ("12.5",)


def test_two_supported_metrics_keep_their_own_values_in_one_sentence() -> None:
    result = guard_caption(
        "Oil rate was 19 m3/day and injection rate was 12.5 m3/day.",
        [{"oil_rate_m3_per_day": 19.0, "injection_rate_m3_per_day": 12.5}],
    )

    assert result.ok is True


def test_rounded_number_passes_within_two_significant_digits() -> None:
    result = guard_caption("Итог по фонду — 11,9 млрд руб.", PAYLOADS)
    assert result.ok is True


def test_invented_number_is_cut() -> None:
    result = guard_caption("Скважина дала 777 555 руб. дохода.", PAYLOADS)
    assert result.ok is False
    assert result.dropped == ("777 555",)
    assert "777 555" not in result.text


def test_formula_number_is_allowed_only_when_formula_matches_recorded_card() -> None:
    formula = "ЧДД = Σ_t FCF_t / (1 + WACC)^(год_t − год_старта)"
    card = {"type": "glossary", "payload": {"formula": formula}}

    assert unsupported_numbers(f"> {formula}", [], [card]) == []
    assert unsupported_numbers("> ЧДД = Σ_t FCF_t / (2 + WACC)^(год_t − год_старта)", [], [card]) == ["2"]
    assert unsupported_numbers(f"> {formula}\nПотоков ровно 1", [], [card]) == ["1"]


def test_dates_are_not_treated_as_numbers() -> None:
    text = "Скважину закрыли в марте 2013 года, а ввели 2007-01-01."
    assert unsupported_numbers(text, collect_numbers(PAYLOADS)) == []


def test_iso_date_alone_is_not_a_number() -> None:
    assert unsupported_numbers("Шаг 2015-01-01.", []) == []


def test_rule_code_is_not_a_number() -> None:
    assert unsupported_numbers("Сработало правило R0 и правило R3.", []) == []


def test_well_number_is_not_a_measurement() -> None:
    assert unsupported_numbers("Скважина 45 закрыта.", []) == []


def test_mass_and_volume_units_do_not_accept_each_others_values() -> None:
    evidence = [{"oil_mass_delta": 12.0, "injection_volume_delta": 50.0}]
    allowed = [12.0, 50.0]

    assert unsupported_numbers("Oil mass was 50 kg.", allowed, evidence) == ["50"]
    assert unsupported_numbers("Injection volume was 12 m³.", allowed, evidence) == ["12"]
    assert guard_caption("Oil mass was 50 kg.", evidence).dropped == ("50",)


def test_recorded_mass_and_volume_values_pass_with_matching_units() -> None:
    evidence = [{"oil_mass_delta": 12.0, "injection_volume_delta": 50.0}]
    text = "Oil mass was 12 kg; injection volume was 50 m³."

    assert unsupported_numbers(text, [12.0, 50.0], evidence) == []


@pytest.mark.parametrize(
    ("claim", "wrong_claim", "wrong_raw"),
    [
        ("Cumulative NPV was 12 RUB.", "Cumulative NPV was 99 RUB.", "99"),
        ("Накопленный ЧДД — 12 руб.", "Накопленный ЧДД — 99 руб.", "99"),
    ],
)
def test_cumulative_npv_uses_its_own_metric_evidence(
    claim: str, wrong_claim: str, wrong_raw: str
) -> None:
    evidence = [{"metrics": [
        {"id": "npv_cumulative", "unit": "RUB", "value": 12.0},
        {"id": "npv", "unit": "RUB", "value": 99.0},
    ]}]

    assert unsupported_numbers(claim, [12.0, 99.0], evidence) == []
    assert unsupported_numbers(wrong_claim, [12.0, 99.0], evidence) == [wrong_raw]


def test_caption_guard_removes_cumulative_npv_borrowed_from_total_npv() -> None:
    result = guard_caption(
        "Cumulative NPV was 99 RUB.",
        [{"metrics": [
            {"id": "npv_cumulative", "unit": "RUB", "value": 12.0},
            {"id": "npv", "unit": "RUB", "value": 99.0},
        ]}],
    )

    assert result.ok is False
    assert "99" not in result.text


@pytest.mark.parametrize(
    ("claim", "wrong_claim", "wrong_raw", "evidence", "right_value", "wrong_value"),
    [
        (
            "The direct link weight was 0.25.",
            "The direct link weight was 0.7.",
            "0.7",
            [{"direct_connection": {"weight": 0.25}, "ood_score": 0.7}],
            0.25,
            0.7,
        ),
        (
            "Вес прямой связи — 0,25.",
            "Вес прямой связи — 0,7.",
            "0,7",
            [{"direct_connection": {"weight": 0.25}, "ood_score": 0.7}],
            0.25,
            0.7,
        ),
        (
            "OOD score is 0.7.",
            "OOD score is 0.25.",
            "0.25",
            [{"direct_connection": {"weight": 0.25}, "ood_score": 0.7}],
            0.7,
            0.25,
        ),
        (
            "Оценка OOD — 0,7.",
            "Оценка OOD — 0,25.",
            "0,25",
            [{"direct_connection": {"weight": 0.25}, "ood_score": 0.7}],
            0.7,
            0.25,
        ),
    ],
)
def test_dimensionless_link_and_ood_metrics_are_grounded_independently(
    claim: str,
    wrong_claim: str,
    wrong_raw: str,
    evidence: list[dict[str, object]],
    right_value: float,
    wrong_value: float,
) -> None:
    assert unsupported_numbers(claim, [right_value, wrong_value], evidence) == []
    assert unsupported_numbers(wrong_claim, [right_value, wrong_value], evidence) == [
        wrong_raw
    ]


def test_decimal_comma_is_understood() -> None:
    result = guard_caption("Доля правила — 0,098 от итога.", PAYLOADS)
    assert result.ok is True


def test_negative_value_from_tool_passes() -> None:
    result = guard_caption("Скважина принесла −20 491 675 руб.", PAYLOADS)
    assert result.ok is True


def test_positive_value_is_not_justified_by_a_negative_measurement() -> None:
    result = guard_caption("The recorded change was 20 491 675 rubles.", [{"delta": -20491675.0}])

    assert result.ok is False
    assert result.dropped == ("20 491 675",)


def test_run_reference_must_match_an_id_in_the_answer_evidence() -> None:
    evidence = [{"run_id": "jarvis-run-2026"}]

    accepted = guard_run_references("Selected run jarvis-run-2026 is active.", evidence, "en")
    rejected = guard_run_references("Selected run other-run-2026 is active.", evidence, "en")

    assert accepted.ok is True
    assert rejected.ok is False
    assert rejected.text == "The run identifier is not confirmed by this answer's evidence cards."


def test_numeric_guard_masks_the_date_like_suffix_of_a_recorded_run_id() -> None:
    evidence = [{"run_id": "jarvis-run-2026"}]

    assert unsupported_numbers("Selected run jarvis-run-2026.", [], evidence) == []


def test_run_reference_guard_does_not_treat_an_agent_rule_as_a_run_id() -> None:
    result = guard_run_references("Rule R0 changed the setpoint.", [], "en")

    assert result.ok is True


def test_run_reference_guard_preserves_markdown_when_dropping_a_sentence() -> None:
    text = "## Summary\n\n- First fact.\n- Run bad-run-2040 is missing.\n- Last fact."

    result = guard_run_references(text, [], "en")

    assert result.ok is False
    assert result.text == "## Summary\n\n- First fact.\n- Last fact."


def test_context_reference_guard_accepts_wells_and_steps_in_evidence() -> None:
    result = guard_context_references(
        "Скважина 13 на шаге 10 соответствует данным.",
        [{"known_wells": ["13"], "known_steps": [0, 10]}],
        "ru",
    )

    assert result.ok is True


def test_context_reference_guard_accepts_date_with_equivalent_format() -> None:
    result = guard_context_references(
        "The recorded response is dated 01.01.2007.",
        [{"known_dates": ["2007-01-01"]}],
        "en",
    )

    assert result.ok is True


def test_context_reference_guard_drops_unrecorded_date() -> None:
    result = guard_context_references(
        "The change happened in 2040.",
        [{"known_dates": ["2007-01-01", "2015-03-01"]}],
        "en",
    )

    assert result.ok is False
    assert result.dropped == ("The change happened in 2040.",)
    assert result.text == "The rule, well, step, or date is not confirmed by this answer's evidence."


def test_context_reference_guard_accepts_year_present_in_known_timeline() -> None:
    result = guard_context_references(
        "The response was recorded in 2015.",
        [{"known_dates": ["2015-03-01", "2015-09-01"]}],
        "en",
    )

    assert result.ok is True


@pytest.mark.parametrize("month", ["January", "Jan"])
def test_context_reference_guard_checks_english_month_and_year(month: str) -> None:
    result = guard_context_references(
        f"The response was recorded in {month} 2015.",
        [{"known_dates": ["2015-01-01", "2015-09-01"]}],
        "en",
    )

    assert result.ok is True


def test_context_reference_guard_drops_unrecorded_english_month_and_year() -> None:
    result = guard_context_references(
        "The response was recorded in Jan 2015.",
        [{"known_dates": ["2015-03-01", "2015-09-01"]}],
        "en",
    )

    assert result.ok is False
    assert result.dropped == ("The response was recorded in Jan 2015.",)


def test_context_reference_guard_checks_rule_ids() -> None:
    result = guard_context_references(
        "Rule R0 was selected.", [{"rule_id": "R0"}], "en"
    )

    assert result.ok is True


def test_context_reference_guard_drops_unknown_rule_id() -> None:
    result = guard_context_references(
        "Rule R9 was selected.", [{"rule_id": "R0"}], "en"
    )

    assert result.ok is False
    assert result.dropped == ("Rule R9 was selected.",)
    assert result.text == "The rule, well, step, or date is not confirmed by this answer's evidence."


def test_tool_failure_guard_removes_success_claim_and_exposes_reason() -> None:
    result = guard_tool_failure_claims(
        "The council completed allocation.",
        [{"type": "error", "payload": {"message": "no-council-step", "next_step": "Check the selected step."}}],
        "en",
    )

    assert result.ok is False
    assert "completed allocation" not in result.text
    assert "no-council-step" in result.text
    assert "Check the selected step." in result.text


def test_tool_failure_guard_keeps_negated_success_claim() -> None:
    result = guard_tool_failure_claims(
        "The report was not generated.",
        [{"type": "error", "payload": {"message": "no-council-step"}}],
        "en",
    )

    assert result.ok is True
    assert result.text == "The report was not generated."


def test_tool_failure_guard_removes_russian_success_claim() -> None:
    result = guard_tool_failure_claims(
        "Отчёт сформирован.",
        [{"type": "error", "payload": {"message": "no-council-step", "next_step": "Проверьте шаг."}}],
        "ru",
    )

    assert result.ok is False
    assert "Отчёт сформирован." not in result.text
    assert "no-council-step" in result.text


def test_tool_failure_guard_keeps_russian_negated_success_claim() -> None:
    text = "Отчёт не сформирован."
    result = guard_tool_failure_claims(
        text, [{"type": "error", "payload": {"message": "no-council-step"}}], "ru"
    )

    assert result.ok is True
    assert result.text == text


def test_tool_failure_guard_does_not_hide_success_from_mixed_tool_results() -> None:
    text = "The report shows the recorded status."
    result = guard_tool_failure_claims(
        text,
        [
            {"type": "error", "payload": {"message": "missing report"}},
            {"type": "metric", "payload": {"value": 10}},
        ],
    )

    assert result.ok is True
    assert result.text == text


def test_tool_failure_guard_removes_only_claim_about_failed_tool() -> None:
    result = guard_tool_failure_claims(
        "Field metrics returned data. The council completed allocation.",
        [
            {"type": "metric", "payload": {"field": {"oil_rate": 12}}},
            {
                "type": "error",
                "payload": {
                    "tool": "council_step",
                    "message": "no-council-step",
                    "next_step": "Check the selected step.",
                },
            },
        ],
        "en",
    )

    assert result.ok is False
    assert result.text == "Field metrics returned data."
    assert result.dropped == ("The council completed allocation.",)


def test_tool_failure_guard_keeps_unrelated_success_claim_in_mixed_results() -> None:
    text = "The field metrics returned data."
    result = guard_tool_failure_claims(
        text,
        [
            {"type": "error", "payload": {"tool": "council_step", "message": "missing"}},
            {"type": "metric", "payload": {"value": 10}},
        ],
        "en",
    )

    assert result.ok is True
    assert result.text == text


@pytest.mark.parametrize(
    ("tool", "subject", "subject_ru"),
    [
        ("well_snapshot", "well snapshot", "снимок скважины"),
        ("well_series", "time series", "временной ряд"),
        ("compare_wells", "well comparison", "сравнение скважин"),
        ("field_metrics", "field metrics", "показатели фонда"),
        ("field_events", "field events", "события фонда"),
        ("rank_wells", "ranking", "рейтинг скважин"),
        ("connectivity", "connectivity", "связи соседей"),
        ("find_patterns", "anomaly findings", "диагностические находки"),
        ("explain_decision", "decision rules", "правила решения"),
        ("decision_journal", "decision journal", "журнал решений"),
        ("rule_impact", "rule impact", "вклад правил"),
        ("compare_scenarios", "scenario comparison", "сравнение сценариев"),
        ("explain_term", "term definition", "определение термина"),
        ("platform_guide", "user guide", "инструкция пользователя"),
        ("run_status", "run status", "статус прогона"),
        ("submission_summary", "submission package", "пакет сдачи"),
        ("search_docs", "documents", "документы"),
        ("system_map", "system architecture", "архитектура системы"),
        ("system_status", "system status", "состояние системы"),
        ("run_history", "run history", "история прогонов"),
        ("run_detail", "run manifest", "манифест прогона"),
        ("compare_runs", "comparison of runs", "сравнение прогонов"),
        ("case_constraints", "case constraints", "ограничения кейса"),
        ("council_step", "council allocation", "распределение квоты"),
        ("physics_report", "physics validation", "физическая проверка"),
    ],
)
def test_tool_failure_guard_covers_every_registered_tool_subject(
    tool: str, subject: str, subject_ru: str
) -> None:
    assert TOOL_SUBJECT_PATTERNS[tool].search(subject)
    assert TOOL_SUBJECT_PATTERNS[tool].search(subject_ru)
    result = guard_tool_failure_claims(
        f"The {subject} were generated.",
        [
            {"type": "error", "payload": {"tool": tool, "message": "unavailable"}},
            {"type": "metric", "payload": {"value": 1}},
        ],
        "en",
    )

    assert result.ok is False
    assert result.dropped == (f"The {subject} were generated.",)

    result_ru = guard_tool_failure_claims(
        f"Данные по теме: {subject_ru} сформированы.",
        [
            {"type": "error", "payload": {"tool": tool, "message": "unavailable"}},
            {"type": "metric", "payload": {"value": 1}},
        ],
        "ru",
    )
    assert result_ru.ok is False
    assert result_ru.dropped == (f"Данные по теме: {subject_ru} сформированы.",)


@pytest.mark.parametrize(
    "text",
    [
        "Скважина 99 показала рост.",
        "Скважина 13 на шаге 99 показала рост.",
        "Well 99 at step 10 had a higher rate.",
    ],
)
def test_context_reference_guard_drops_unrecorded_well_or_step(text: str) -> None:
    result = guard_context_references(
        text,
        [{"known_wells": ["13"], "known_steps": [10]}],
        "en",
    )

    assert result.ok is False
    assert result.dropped == (text,)
    assert result.text == "The rule, well, step, or date is not confirmed by this answer's evidence."


def test_several_invented_numbers_all_cut() -> None:
    result = guard_caption("Было 5555 и стало 6666.", PAYLOADS)
    assert result.ok is False
    assert set(result.dropped) == {"5555", "6666"}


def test_caption_without_numbers_passes() -> None:
    result = guard_caption("Скважина перестала окупать содержание.", [])
    assert result.ok is True
    assert result.text == "Скважина перестала окупать содержание."


def test_collect_numbers_walks_nested_structures() -> None:
    found = collect_numbers({"a": [{"b": 7.0}], "c": {"d": [1, 2]}})
    assert 7.0 in found
    assert 1.0 in found
    assert 2.0 in found


def test_booleans_are_not_numbers() -> None:
    assert collect_numbers({"flag": True}) == set()


MANIFEST = {
    "run_id": "jarvis-run",
    "status": "ready_to_submit",
    "schedule_hash": "0" * 64,
    "predicted_npv": 12345678.5,
    "verified_npv": 11873122324.91,
    "sound": True,
    "iterations": 240,
    "search_strategy": "cmaes-restart",
    "model_version": None,
}
CLAIMED = {
    "canonical_schedule_hash": "0" * 64,
    "claimed_npv_rub": 11873122324.91,
    "source_run_id": "jarvis-run",
    "created_at": "2026-09-09T10:00:00+00:00",
}


def test_claimed_npv_of_the_package_is_not_cut() -> None:
    result = guard_caption(
        "Заявленный ЧДД пакета — 11 873 676 460 руб.", [], [MANIFEST, CLAIMED]
    )
    assert result.ok is True
    assert result.dropped == ()
    assert "11 873 676 460" in result.text


def test_manifest_prediction_is_not_cut() -> None:
    result = guard_caption("Прогноз суррогата — 12 345 679 руб.", [], [MANIFEST])
    assert result.ok is True


def test_manifest_iteration_count_is_not_cut() -> None:
    result = guard_caption("Поиск занял 240 итераций.", [], [MANIFEST])
    assert result.ok is True


def test_invented_number_is_still_cut_next_to_the_package() -> None:
    result = guard_caption(
        "Заявленный ЧДД — 11 873 676 460 руб., а запас 777 555 руб.",
        [],
        [MANIFEST, CLAIMED],
    )
    assert result.ok is False
    assert result.dropped == ("777 555",)
    assert "11 873 676 460" in result.text
    assert "777 555" not in result.text


def test_package_numbers_are_not_allowed_without_the_evidence() -> None:
    result = guard_caption("Заявленный ЧДД — 11 873 676 460 руб.", [])
    assert result.ok is False


def test_allowed_numbers_merges_payloads_and_evidence() -> None:
    allowed = allowed_numbers(PAYLOADS, [CLAIMED])
    assert 11873122324.91 in allowed
    assert 1161713780.758579 in allowed


def test_rejected_plan_cannot_be_described_as_accepted() -> None:
    payload = {"plan_check": {"sound": False}}
    result = guard_plan_status("План принят, расчёт OPM завершился.", [payload], "ru")
    assert result.ok is False
    assert "План не прошёл" in result.text
    assert "принят" not in result.text


def test_rejected_plan_cannot_be_described_as_sound_in_english() -> None:
    payload = {"plan_check": {"sound": False}}
    result = guard_plan_status("The plan is sound.", [payload])

    assert result.ok is False
    assert result.text == "The plan did not pass the eligibility check."
    assert result.dropped == ("The plan is sound.",)


@pytest.mark.parametrize(
    ("text", "lang"),
    [
        ("The plan is sound, but it was not submitted for review.", "en"),
        ("План допущен, но проверка ещё не опубликована.", "ru"),
    ],
)
def test_unrelated_negation_in_another_clause_does_not_hide_rejected_plan_claim(
    text: str, lang: str
) -> None:
    result = guard_plan_status(text, [{"plan_check": {"sound": False}}], lang)

    assert result.ok is False
    assert result.dropped == (text,)


def test_explicit_rejection_survives_plan_status_guard() -> None:
    payload = {"plan_check": {"sound": False}}
    result = guard_plan_status("План не прошёл проверку допуска.", [payload], "ru")
    assert result.ok is True
    assert result.text == "План не прошёл проверку допуска."


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        ({"acceptance": {"verdict": "unknown"}}, "Допуск плана не подтверждён"),
        ({"plan_check": {"sound": True}}, "Допуск плана не подтверждён"),
        ({}, "Допуск плана не подтверждён"),
    ],
)
def test_positive_plan_status_requires_recorded_acceptance(payload: dict, expected: str) -> None:
    result = guard_plan_status("План принят.", [payload], "ru")

    assert result.ok is False
    assert result.text.startswith(expected)
    assert result.dropped == ("План принят.",)


def test_recorded_acceptance_supports_scoped_positive_claim() -> None:
    payload = {"acceptance": {"verdict": "accepted_for_recorded_checks"}}

    result = guard_plan_status("План принят по записанным проверкам.", [payload], "ru")

    assert result.ok is True
    assert result.text == "План принят по записанным проверкам."


def test_mixed_verdicts_cannot_support_unscoped_status_claim() -> None:
    payloads = [
        {"acceptance": {"verdict": "accepted_for_recorded_checks"}},
        {"acceptance": {"verdict": "rejected"}},
    ]

    result = guard_plan_status("План принят.", payloads, "ru")

    assert result.ok is False
    assert result.text == "Допуск плана не подтверждён записанной проверкой."


@pytest.mark.parametrize(
    ("payload", "text", "expected"),
    [
        ({"acceptance": {"verdict": "unknown"}}, "План отклонён.", "Допуск плана не подтверждён записанной проверкой."),
        ({"acceptance": {"verdict": "accepted_for_recorded_checks"}}, "План не прошёл проверку допуска.", "План принят по записанным проверкам."),
        ({}, "The plan was rejected.", "Допуск плана не подтверждён записанной проверкой."),
    ],
)
def test_negative_plan_status_requires_recorded_rejection(payload: dict, text: str, expected: str) -> None:
    result = guard_plan_status(text, [payload], "ru")

    assert result.ok is False
    assert result.text == expected


def test_recorded_decision_does_not_support_causality_or_optimality() -> None:
    payload = {
        "record_status": "observation-and-evidence-recorded",
        "decision_summary": {"basis": "recorded-events; no causal inference"},
    }
    result = guard_decision_claims(
        "R0 caused the change because the well was constrained. It was the optimal choice.",
        [payload],
        "en",
    )
    assert result.ok is False
    assert "causality or optimality" in result.text
    assert "caused" not in result.text


def test_decision_claim_guard_is_scoped_to_recorded_decisions() -> None:
    result = guard_decision_claims("Because the rule is documented.", [{"source": "guide"}], "en")
    assert result.ok is True
    assert result.text == "Because the rule is documented."


def test_decision_claim_guard_covers_trace_journal_without_causal_explanation() -> None:
    result = guard_decision_claims(
        "The quota caused the change. The journal records the selected rule.",
        [{"source": "trace.json", "facts": [{"decision": "SET_LRAT"}], "why": None}],
        "en",
    )

    assert result.ok is False
    assert result.dropped == ("The quota caused the change.",)
    assert result.text == "The journal records the selected rule."


def test_negation_in_another_clause_does_not_hide_unsupported_optimality() -> None:
    payload = {"record_status": "observation-and-evidence-recorded"}

    result = guard_decision_claims(
        "The journal does not explain why this was selected, but this was the optimal plan.",
        [payload],
        "en",
    )

    assert result.ok is False
    assert "optimal plan" not in result.text


@pytest.mark.parametrize(
    ("text", "lang"),
    [
        ("This is not impossible: the quota drove the change.", "en"),
        ("Это не исключено: квота привела к изменению.", "ru"),
        ("The plan is not rejected because it is the best option.", "en"),
    ],
)
def test_unrelated_negation_nearby_does_not_hide_decision_claim(text: str, lang: str) -> None:
    result = guard_decision_claims(
        text, [{"record_status": "observation-and-evidence-recorded"}], lang
    )

    assert result.ok is False
    assert result.dropped == (text,)


@pytest.mark.parametrize(
    "text",
    [
        "The journal does not explain why the quota changed the rate.",
        "Журнал не подтверждает оптимальность плана.",
    ],
)
def test_directly_negated_decision_claim_is_kept(text: str) -> None:
    result = guard_decision_claims(
        text,
        [{"record_status": "observation-and-evidence-recorded"}],
        "ru" if any("а" <= char.lower() <= "я" for char in text) else "en",
    )

    assert result.ok is True
    assert result.text == text


def test_russian_contrast_clause_does_not_hide_unsupported_causality() -> None:
    payload = {"record_status": "observation-and-evidence-recorded"}

    result = guard_decision_claims(
        "Причина не установлена, однако правило вызвало изменение.", [payload], "ru"
    )

    assert result.ok is False
    assert "вызвало изменение" not in result.text


@pytest.mark.parametrize(
    ("text", "lang"),
    [
        (
            "The journal does not establish causality, and the quota drove the change.",
            "en",
        ),
        (
            "Причина не установлена, и квота привела к изменению.",
            "ru",
        ),
        (
            "Журнал не подтверждает оптимальность, при этом это лучший план.",
            "ru",
        ),
    ],
)
def test_negation_in_conjoined_clause_does_not_hide_unsupported_claim(
    text: str, lang: str
) -> None:
    result = guard_decision_claims(
        text, [{"record_status": "observation-and-evidence-recorded"}], lang
    )

    assert result.ok is False
    assert result.dropped == (text,)


@pytest.mark.parametrize(
    ("claim", "expected"),
    [
        ("The change was driven by the constraint.", "driven by"),
        ("The choice was based on the constraint.", "based on"),
        ("The decision follows from rule R0.", "follows from"),
        ("The decision was grounded in the quota.", "grounded in"),
        ("The constraint is why the rate changed.", "why"),
        ("This was the best plan.", "best plan"),
        ("Изменение произошло благодаря ограничению.", "благодаря"),
        ("Это лучший план.", "лучший план"),
        ("Изменение объясняется правилом.", "объясняется"),
        ("Ограничение приводит к изменению режима.", "приводит к"),
        ("Выбор обусловлен квотой.", "обусловлен"),
        ("Решение основано на ограничении.", "основано на"),
        ("Выбор сделан исходя из квоты.", "исходя из"),
        ("Правило послужило причиной изменения.", "послужило причиной"),
        ("Ограничение позволило выбрать режим.", "позволило"),
        ("Квота стала главным фактором изменения режима.", "главным фактором"),
        ("The new plan outperforms the submitted plan.", "outperforms"),
        ("The plan dominates the alternative.", "dominates"),
        ("This is the highest NPV plan.", "highest NPV"),
        ("That is a top-performing option.", "top-performing"),
        ("The quota accounted for the rate change.", "accounted for"),
        ("The quota is responsible for the change.", "responsible for"),
        ("The change is attributable to the quota.", "attributable to"),
        ("The quota causally explains the change.", "causally"),
        ("The constraint explains why the rate changed.", "explains why"),
        ("The constraint explains the selected rate.", "explains the selected rate"),
        ("Ограничение объясняет выбор режима.", "объясняет выбор"),
        ("The change resulted from the quota.", "resulted from"),
        ("The quota was the key driver of the change.", "key driver"),
        ("The constraint was the primary factor behind the selected rate.", "primary factor"),
        ("This is the better plan.", "better plan"),
        ("This option is the most profitable.", "most profitable"),
        ("This alternative is more profitable.", "more profitable"),
        ("This performs better than the recorded option.", "performs better"),
        ("The policy maximizes NPV.", "maximizes"),
        ("Этот вариант лучше альтернативы.", "лучше"),
        ("Этот план эффективнее.", "эффективнее"),
        ("Такой вариант более выгодный.", "более выгодный"),
        ("Этот подход максимизирует ЧДД.", "максимизирует"),
        ("Policy drove the rate change.", "drove"),
        ("The quota contributed to the rate change.", "contributed to"),
        ("The rule had an impact on the selected rate.", "impact on"),
        ("The quota affects the selected rate.", "affects"),
        ("The rule affected the selected rate.", "affected"),
        ("The quota had an effect on the selected rate.", "effect on"),
        ("Ограничение повлияло на выбор режима.", "повлияло на"),
        ("Ограничение влияет на режим.", "влияет на"),
        ("Это идеальный план.", "идеальный план"),
        ("The rule triggered a schedule change.", "triggered"),
        ("Команда изменилась, поскольку сработало ограничение.", "поскольку"),
        ("Выбрали его не только потому что дебит выше.", "потому что"),
        ("It was not only because the well had a higher rate.", "because"),
        ("The constraint enabled the rate change.", "enabled"),
        ("The quota gave rise to the schedule change.", "gave rise to"),
        ("The plan beats the alternative.", "beats the alternative"),
        ("The candidate wins over the baseline.", "wins over the baseline"),
        ("Ограничение способствовало изменению режима.", "способствовало"),
        ("Этот вариант превосходит альтернативу.", "превосходит"),
    ],
)
def test_indirect_causal_and_optimality_claims_are_removed_for_recorded_decisions(
    claim: str, expected: str
) -> None:
    result = guard_decision_claims(
        claim,
        [{"record_status": "observation-and-evidence-recorded"}],
        "ru" if any("а" <= char.lower() <= "я" for char in claim) else "en",
    )

    assert result.ok is False
    assert expected not in result.text
