from __future__ import annotations

from typing import Mapping

METRIC_UNITS: Mapping[str, str] = {
    "liquid_rate": "m3/day",
    "injection_rate": "m3/day",
    "watercut": "fraction",
    "bhp": "bar",
    "npv": "RUB",
    "active_wells": "wells",
    "production": "m3/day",
    "injection": "m3/day",
    "compensation": "fraction",
    "npv_cumulative": "RUB",
}

METRIC_LABELS: Mapping[str, Mapping[str, str]] = {
    "liquid_rate": {"ru": "дебит жидкости", "en": "liquid rate"},
    "injection_rate": {"ru": "дебит закачки", "en": "injection rate"},
    "watercut": {"ru": "обводнённость", "en": "water cut"},
    "bhp": {"ru": "забойное давление", "en": "bottomhole pressure"},
    "npv": {"ru": "ЧДД", "en": "NPV"},
    "active_wells": {"ru": "действующий фонд", "en": "active well stock"},
    "production": {"ru": "добыча жидкости", "en": "liquid production"},
    "injection": {"ru": "суммарная закачка фонда", "en": "total field injection"},
    "compensation": {"ru": "компенсация", "en": "compensation"},
    "npv_cumulative": {"ru": "накопленный ЧДД", "en": "cumulative NPV"},
}

EVENT_LABELS: Mapping[str, Mapping[str, str]] = {
    "COMMISSIONED": {"ru": "ввод", "en": "commissioned"},
    "ROLE_CHANGE": {"ru": "перевод в нагнетательные", "en": "converted to injection"},
    "SHUT": {"ru": "остановка", "en": "shut in"},
}

RULE_NAMES: Mapping[str, Mapping[str, str]] = {
    "R0": {"ru": "Порог рентабельности", "en": "Profitability threshold"},
    "R1": {"ru": "Ценность закачки", "en": "Value of injection"},
    "R2": {"ru": "Разгон чистых, придушивание обводнённых", "en": "Speed up clean, throttle watered"},
    "R3": {"ru": "Остановка после месяцев убытка", "en": "Shut in after months in loss"},
    "R4": {"ru": "Граница типоразмера ЭЦН", "en": "ESP size boundary"},
    "R5": {"ru": "Коридор компенсации участка", "en": "Area compensation corridor"},
    "R6": {"ru": "Перевод в нагнетательные", "en": "Conversion to injection"},
    "R7": {"ru": "Циклика высокообводнённых", "en": "Cycling heavily watered wells"},
}

TITLES: Mapping[str, Mapping[str, str]] = {
    "well": {"ru": "Скважина {well}", "en": "Well {well}"},
    "well_comparison": {"ru": "Сравнение скважин {a} и {b}", "en": "Compare wells {a} and {b}"},
    "series": {"ru": "{label} — скважина {well}", "en": "{label} — well {well}"},
    "field": {"ru": "Фонд на {date}", "en": "Field on {date}"},
    "events": {"ru": "События фонда: {a} — {b}", "en": "Field events: {a} — {b}"},
    "rank_asc": {"ru": "{count} худших по {label}", "en": "{count} worst by {label}"},
    "rank_desc": {"ru": "{count} лучших по {label}", "en": "{count} best by {label}"},
    "rule": {"ru": "Правило {rule} — скважина {well}", "en": "Rule {rule} — well {well}"},
    "decision_evidence": {"ru": "Основания решения — скважина {well}, шаг {step}", "en": "Decision evidence — well {well}, step {step}"},
    "rule_one": {"ru": "Вклад правила {rule}", "en": "Contribution of rule {rule}"},
    "rule_all": {"ru": "Вклад правил в ЧДД", "en": "Rule contributions to NPV"},
    "connectivity": {"ru": "Связи скважины {well}", "en": "Links of well {well}"},
    "compare": {"ru": "{a} против {b}", "en": "{a} versus {b}"},
    "patterns_well": {"ru": "Находки по скважине {well}", "en": "Findings for well {well}"},
    "patterns_field": {"ru": "Диагностические находки", "en": "Diagnostic findings"},
    "tool_failed": {"ru": "Не удалось: {tool}", "en": "Tool failed: {tool}"},
    "run_status": {"ru": "Прогон {run_id}", "en": "Run {run_id}"},
    "submission": {"ru": "Пакет сдачи — прогон {run_id}", "en": "Submission package — run {run_id}"},
}

TOOL_NAMES: Mapping[str, Mapping[str, str]] = {
    "draft_case": {"ru": "черновик нового кейса", "en": "new case proposal"},
    "draft_alternative": {"ru": "черновик альтернативы", "en": "alternative proposal"},
    "well_snapshot": {"ru": "снимок скважины", "en": "well snapshot"},
    "well_series": {"ru": "ряд скважины", "en": "well time series"},
    "compare_wells": {"ru": "сравнение скважин", "en": "well comparison"},
    "field_metrics": {"ru": "метрики фонда", "en": "field metrics"},
    "field_events": {"ru": "события фонда", "en": "field events"},
    "rank_wells": {"ru": "рейтинг скважин", "en": "well ranking"},
    "connectivity": {"ru": "связи скважины", "en": "well connectivity"},
    "find_patterns": {"ru": "диагностика", "en": "diagnostics"},
    "explain_decision": {"ru": "объяснение решения", "en": "decision explanation"},
    "decision_journal": {"ru": "журнал решений", "en": "decision journal"},
    "rule_impact": {"ru": "вклад правил", "en": "rule impact"},
    "compare_scenarios": {"ru": "сравнение сценариев", "en": "scenario comparison"},
    "explain_term": {"ru": "терминология", "en": "terminology"},
    "platform_guide": {"ru": "справка по интерфейсу", "en": "interface guide"},
    "run_status": {"ru": "статус прогона", "en": "run status"},
    "submission_summary": {"ru": "пакет сдачи", "en": "submission package"},
    "search_docs": {"ru": "поиск по документам", "en": "document search"},
    "system_map": {"ru": "карта системы", "en": "system map"},
    "system_status": {"ru": "сводка системы", "en": "system overview"},
    "run_history": {"ru": "история прогонов", "en": "run history"},
    "run_detail": {"ru": "детали прогона", "en": "run details"},
    "compare_runs": {"ru": "сравнение прогонов", "en": "run comparison"},
    "case_constraints": {"ru": "ограничения кейса", "en": "case constraints"},
    "council_step": {"ru": "решения совета", "en": "council decisions"},
    "physics_report": {"ru": "отчёт физической проверки", "en": "physics report"},
}

RUN_STATUS_LABELS: Mapping[str, Mapping[str, str]] = {
    "searched": {"ru": "поиск выполнен", "en": "searched"},
    "verified": {"ru": "проверен на OPM", "en": "verified"},
    "rejected": {"ru": "отклонён", "en": "rejected"},
    "ready_to_submit": {"ru": "готов к сдаче", "en": "ready to submit"},
}


def pick(table: Mapping[str, Mapping[str, str]], key: str, lang: str) -> str:
    entry = table.get(key)
    if entry is None:
        return key
    return entry.get(lang, entry.get("ru", key))


def title(key: str, lang: str, **values: object) -> str:
    template = pick(TITLES, key, lang)
    return template.format(**values)
