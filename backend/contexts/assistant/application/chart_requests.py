from __future__ import annotations

import re
from typing import Any, Mapping

from backend.contexts.assistant.domain.console_context import ConsoleContext

# Only concrete requests to display data. Educational questions, negations,
# comparisons and missing targets stay with the conversational planner.
_SHOW = re.compile(r'\b(?:покажи(?:те)?|построй(?:те)?|выведи(?:те)?|show|plot|display)\b', re.I)
_CHART = re.compile(r'\b(?:график[а-яё]*|временн[а-яё]*\s+ряд[а-яё]*|charts?|plots?|time\s+series)\b', re.I)
_NOT_DATA = re.compile(r'(?:\bне\s+(?:показывай|покажи|строй|построй)|\b(?:do\s+not|don.t)\s+(?:show|plot)|\b(?:как\s+работает|что\s+такое|what\s+.*\s+means|how\s+.*\s+works|построени[а-яё]*))', re.I)
_WELL = re.compile(r'\b(?:скважин[а-яё]*|wells?)\s*(?:№|#)?\s*(\d+)\b', re.I)
_WELL_LIST = re.compile(r'\b(?:скважин[а-яё]*|wells?)\s*(?:№|#)?\s*\d+\s*(?:,|и\b|and\b|to\b|[-–])\s*\d+', re.I)
_RUN = re.compile(r'\b(?:прогон[а-яё]*|run)\s+[`\"\']?([a-z0-9][a-z0-9_.-]*)', re.I)
_RUN_AFTER_FOR = re.compile(r'\b(?:для|for|из|from)\s+[`\"\']?((?=[a-z0-9_.-]*[-_])[a-z0-9][a-z0-9_.-]*)', re.I)
_RUN_MENTION = re.compile(r"\b(?:прогон[а-яё]*|runs?)\b", re.I)
_UNSUPPORTED_METRIC = re.compile(r"нефт[а-яё]*|\boil\b|reservoir|пластов[а-яё]*", re.I)
_INTERVAL = re.compile(r"\b(?:шаг[а-яё]*|steps?)\s*(\d+)\s*(?:[-–]|до|to)\s*(\d+)\b", re.I)
_DATE = re.compile(r"\b(?:19|20)\d{2}\b")
_STEP = re.compile(r'\b(?:шаг[а-яё]*|step)\s*(\d+)\b', re.I)
_STEP_LIST = re.compile(r'\b(?:шаг[а-яё]*|steps?)\s*\d+\s*(?:,|и\b|and\b|or\b|или\b)\s*\d+', re.I)
_RELATIVE_STEP = re.compile(r'(?:следующ[а-яё]*|предыдущ[а-яё]*|next|previous)\s+(?:шаг[а-яё]*|step)', re.I)
_LATEST_RUN = re.compile(r'последн[а-яё]*\s+прогон|(?:latest|newest)\s+run', re.I)
_LINKS = re.compile(r'\b(?:связ[а-яё]*|connectivity|connections?|neighbou?rs?)\b', re.I)
_JOURNAL = re.compile(r'журнал[а-яё]*\s+решени[а-яё]*|decision\s+journal', re.I)
_EXPLAIN = re.compile(r'\b(?:раскрой|покажи|выведи|расскажи|объясни|show|explain|display)\b', re.I)
_WHY_SELECTED = re.compile(r'(?:почему[^?!.]*скважин[^?!.]*выбран|why[^?!.]*well[^?!.]*(?:chosen|selected))', re.I)
_NO_EXPLANATION = re.compile(r'не\s+(?:раскрывай|раскрой|объясняй|объясни|рассказывай|расскажи)|(?:do\s+not|don.t)\s+(?:explain|display)', re.I)
_RUN_IN = re.compile(r'\b(?:в|in|of)\s+[`\"\']?((?=[a-z0-9_.-]*[-_])[a-z0-9][a-z0-9_.-]*)', re.I)
_METRICS = (
    ('injection_rate', re.compile(r'закач[а-яё]*|нагнетан[а-яё]*|\binjection\b', re.I)),
    ('liquid_rate', re.compile(r'жидкост[а-яё]*|\bliquid\b', re.I)),
    ('watercut', re.compile(r'обводн[а-яё]*|water\s*cut', re.I)),
    ('bhp', re.compile(r'давлен[а-яё]*|\bbhp\b|pressure', re.I)),
)


def journal_tool_preset(question: str, console: ConsoleContext) -> tuple[tuple[str, Mapping[str, Any]], ...]:
    """Retrieve one unambiguous recorded journal before asking for prose."""
    intent = (_JOURNAL.search(question) and _EXPLAIN.search(question)) or _WHY_SELECTED.search(question)
    if not intent or _NOT_DATA.search(question) or _NO_EXPLANATION.search(question):
        return ()
    if _INTERVAL.search(question) or _DATE.search(question) or _WELL_LIST.search(question) or _STEP_LIST.search(question) or _RELATIVE_STEP.search(question):
        return ()
    wells = set(_WELL.findall(question))
    steps = set(_STEP.findall(question))
    runs = {match.rstrip('.') for pattern in (_RUN, _RUN_AFTER_FOR, _RUN_IN) for match in pattern.findall(question)}
    if len(wells) > 1 or len(steps) > 1 or len(runs) > 1:
        return ()
    if not runs and _LATEST_RUN.search(question):
        return ()
    well = next(iter(wells), None) or console.selected_well
    run = next(iter(runs), None) or console.run_id
    if not well or not run:
        return ()
    step = int(next(iter(steps))) if steps else console.step
    return (('decision_journal', {'well': well, 'step': 0 if step is None else step, 'run_id': run}),)


def chart_tool_preset(question: str, console: ConsoleContext) -> tuple[tuple[str, Mapping[str, Any]], ...]:
    if not _SHOW.search(question) or not _CHART.search(question) or _NOT_DATA.search(question):
        return ()
    if _UNSUPPORTED_METRIC.search(question) or _STEP_LIST.search(question) or _RELATIVE_STEP.search(question):
        return ()
    interval = _INTERVAL.search(question)
    if _DATE.search(question) or (re.search(r"\b(?:шаг[а-яё]*|steps?)\b", question, re.I) and not interval and _STEP.search(question) is None and not re.search(r"какой|какая|what|which", question, re.I)):
        return ()
    named = set(_WELL.findall(question))
    if len(named) > 1 or _WELL_LIST.search(question):
        return ()
    well = next(iter(named), None) or console.selected_well
    if not well:
        return ()
    metrics = [name for name, pattern in _METRICS if pattern.search(question)]
    runs = {match.rstrip('.') for pattern in (_RUN, _RUN_AFTER_FOR) for match in pattern.findall(question)}
    if len(runs) > 1:
        return ()
    if not runs and _LATEST_RUN.search(question):
        return ()
    run = next(iter(runs), None) or console.run_id
    if not run and _RUN_MENTION.search(question):
        return ()
    if run:
        # The recorded journal card already carries the run-backed input rate
        # and final scheduled targets. It must not be replaced by showcase data.
        # Explicit metrics require the planner to check the recorded role and
        # availability; this chart must not substitute a different metric.
        if interval or metrics:
            return ()
        named_step = _STEP.search(question)
        step = int(named_step.group(1)) if named_step else console.step
        tools: list[tuple[str, Mapping[str, Any]]] = [
            ('decision_journal', {'well': well, 'step': 0 if step is None else step, 'run_id': run})
        ]
    else:
        bounds = {'from_step': int(interval.group(1)), 'to_step': int(interval.group(2))} if interval else {}
        tools = [('well_series', {'well': well, **bounds, **({'metric': metric} if metric else {})})
                 for metric in (metrics or [None])]
    if _LINKS.search(question):
        tools.append(('connectivity', {'well': well}))
    return tuple(tools)
