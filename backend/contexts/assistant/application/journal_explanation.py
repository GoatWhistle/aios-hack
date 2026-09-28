"""Render recorded journal facts when generated prose cannot be verified.

This is a view of authoritative tool fields, like the journal card itself.
It never fills missing measurements from model prose or infers why an event won.
"""
from __future__ import annotations

from math import isfinite
from typing import Any, Mapping, Sequence


def _number(value: Any, unknown: str) -> str:
    if isinstance(value, (int, float)) and not isinstance(value, bool) and isfinite(value):
        return format(value, ".6g")
    return unknown


def journal_explanation(payload: Mapping[str, Any], lang: str = "ru") -> str | None:
    if not isinstance(payload.get("decision_summary"), Mapping) or not payload.get("record_status"):
        return None
    ru = lang == "ru"
    unknown = "не записано" if ru else "not recorded"
    labels = (
        ("Что записано в журнале", "Recorded journal facts"),
        ("Скважина", "Well"),
        ("шаг", "step"),
        ("дата", "date"),
    )
    pick = lambda pair: pair[0 if ru else 1]
    well = str(payload.get("well") or unknown)
    step = _number(payload.get("step"), unknown)
    date = str(payload.get("date") or unknown)
    lines = [
        f"### {pick(labels[0])}", "",
        f"{pick(labels[1])} {well}, {pick(labels[2])} {step}, {pick(labels[3])} {date}.",
        f"{'Прогон' if ru else 'Run'}: `{payload.get('run_id') or unknown}`.", "",
    ]
    observation = payload.get("input_observation")
    observation = observation if isinstance(observation, Mapping) else {}
    role = {"INJ": ("нагнетательная", "injector"), "PROD": ("добывающая", "producer")}.get(observation.get("role"))
    open_flag = observation.get("is_open")
    state = ("открыта", "open") if open_flag is True else ("закрыта", "closed") if open_flag is False else None
    if role is not None or state is not None:
        lines.append(f"- {'Режим' if ru else 'Mode'}: {pick(role) if role else unknown}; {pick(state) if state else unknown}.")
    observed_rate = (
        ("liquid_rate_m3_per_day", ("Исходный измеренный дебит жидкости", "Input measured liquid rate"))
        if observation.get("role") == "PROD" else
        ("injection_rate_m3_per_day", ("Исходная измеренная закачка", "Input measured injection"))
    )
    for key, label in (("setpoint_m3_per_day", ("Исходная уставка", "Observed setpoint")), observed_rate):
        value = _number(observation.get(key), unknown)
        unit = (" м³/сут" if ru else " m3/day") if value != unknown else ""
        lines.append(f"- {pick(label)}: {value}{unit}.")
    limit = _number(payload.get("field_injection_limit_m3_per_day"), unknown)
    if limit != unknown:
        lines.append(f"- {'Лимит закачки фонда' if ru else 'Field injection limit'}: {limit}{' м³/сут' if ru else ' m3/day'}.")
    facts = payload.get("rule_facts")
    facts = facts if isinstance(facts, Sequence) and not isinstance(facts, str) else ()
    levels = {"FIELD": ("поле", "field"), "GROUP": ("группа", "group"), "WELL": ("скважина", "well")}
    for fact in facts:
        if not isinstance(fact, Mapping) or not isinstance(fact.get("entry"), Mapping):
            continue
        entry = fact["entry"]
        inputs = entry.get("inputs")
        inputs = inputs if isinstance(inputs, Mapping) else {}
        level = str(fact.get("level") or "")
        prefix = f"{entry.get('rule') or unknown} ({pick(levels.get(level, (unknown, unknown)))})"
        value_key, value_name = {
            "FIELD": ("water_ceiling_m3_per_day", ("предел закачки", "injection ceiling")),
            "GROUP": ("target_rate_m3_per_day", ("цель", "target")),
            "WELL": ("applied_value_m3_per_day", ("предложение исполнителя", "executor proposal")),
        }.get(level, ("target_rate_m3_per_day", ("цель", "target")))
        value = _number(inputs.get(value_key), unknown)
        unit = (" м³/сут" if ru else " m3/day") if value != unknown else ""
        detail = f"{pick(value_name)} {value}{unit}"
        if level == "GROUP" and entry.get("rule") == "R5":
            compensation = _number(inputs.get("compensation"), unknown)
            low = _number(inputs.get("corridor_low"), unknown)
            high = _number(inputs.get("corridor_high"), unknown)
            corridor = f"{low}–{high}" if low != unknown and high != unknown else unknown
            detail += f"; {'компенсация' if ru else 'compensation'} {compensation}; {'коридор' if ru else 'corridor'} {corridor}"
        lines.append(f"- {prefix}: {detail}.")
    if not facts:
        lines.append("- Предложения правил не записаны." if ru else "- Rule proposals are not recorded.")
    events = payload.get("final_schedule_events")
    events = events if isinstance(events, Sequence) and not isinstance(events, str) else ()
    final: list[str] = []
    for event in events:
        if not isinstance(event, Mapping):
            continue
        kind = str(event.get("kind") or unknown)
        if kind in {"OPEN", "SHUT", "CONVERT_INJ"}:
            final.append(f"`{kind}`")
        else:
            value = _number(event.get("value"), unknown)
            unit = (" м³/сут" if ru else " m3/day") if kind in {"SET_RATE", "SET_LRAT"} and value != unknown else ""
            final.append(f"`{kind}` {value}{unit}")
    lines.extend(["", f"{'Итоговое расписание' if ru else 'Final schedule'}: {'; '.join(final) or unknown}.", ""])
    if final:
        lines.append("Уставка расписания — целевое значение, а не измеренный отклик OPM." if ru else "A scheduled target is not a measured OPM response.")
    lines.append(
        "Отдельная причина расхождения предложений и итоговой команды не записана. Причинность и оптимальность этим журналом не доказаны."
        if ru else
        "A separate reason for the difference between proposals and the final command is not recorded. This journal does not prove causality or optimality."
    )
    if payload.get("projection_status") == "not-recorded-separately":
        lines.append("Проекция отдельно не записана." if ru else "Projection is not separately recorded.")
    return "\n".join(lines)
