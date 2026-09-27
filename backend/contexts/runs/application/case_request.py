"""Strict natural-language drafts for the bounded web-run case editor.

This parser only drafts a single well outage. It never starts a run; the caller
must present the returned constraints to a person for review and confirmation.
"""

from __future__ import annotations

import copy
import re
from collections.abc import Collection, Mapping, Sequence
from datetime import date, datetime
from typing import Any

from backend.contexts.constraints.infrastructure.constraints_io import constraints_from_json


class CaseDraftError(ValueError):
    """The request is ambiguous or outside the supported case-editing subset."""


_DATE = r"(?:\d{4}-\d{2}-\d{2}|\d{1,2}\.\d{1,2}\.\d{4})"
_DATE_RANGE = re.compile(
    rf"(?:\bfrom\s+({_DATE})\s+to\s+({_DATE})\b|\bс\s+({_DATE})\s+(?:по|до)\s+({_DATE})\b)",
    re.IGNORECASE,
)
_WELL = re.compile(
    r"\b(?:well|скв(?:ажин[ауы]?|\.?))\s*(?:№|#)?\s*([\w-]+)",
    re.IGNORECASE,
)
_OUTAGE = re.compile(
    r"\b(?:outage|shut[ -]?in|stop(?:ped|ping)?|останов\w*|отключ\w*|просто\w*)\b",
    re.IGNORECASE,
)
_LIMIT_TARGETS = (
    (
        "injection_limits",
        re.compile(r"(?:лимит\w*\s+закачк\w*|огранич\w*\s+закачк\w*|injection\s+limit)", re.I),
    ),
    (
        "liquid_limits",
        re.compile(r"(?:лимит\w*\s+(?:дебит\w*\s+)?жидкост\w*|liquid(?:\s+rate)?\s+limit)", re.I),
    ),
)
_RATE_VALUE = re.compile(
    r"(?<![\w.-])(\d+(?:[.,]\d+)?)\s*(?:m(?:3|³)\s*/\s*day|м(?:3|³)\s*/\s*(?:сут(?:ки)?|день))\b",
    re.I,
)
_YEAR = re.compile(r"(?:\bfor\s+|\b(?:в|за|на)\s+)(20\d{2})(?:\s*(?:г(?:од(?:у|а)?)?\.?))?\b", re.I)


def _iso_date(raw: str) -> str:
    try:
        parsed = (
            datetime.strptime(raw, "%Y-%m-%d").date()
            if "-" in raw
            else datetime.strptime(raw, "%d.%m.%Y").date()
        )
    except ValueError as error:
        raise CaseDraftError(f"date {raw!r} is not a valid calendar date") from error
    return parsed.isoformat()


def _dates_from_request(text: str) -> tuple[str, str]:
    matches = list(_DATE_RANGE.finditer(text))
    if len(matches) != 1:
        raise CaseDraftError(
            "give exactly one date range, for example “с 01.01.2010 по 01.03.2010” "
            "or “from 2010-01-01 to 2010-03-01”"
        )
    match = matches[0]
    start = match.group(1) or match.group(3)
    end = match.group(2) or match.group(4)
    return _iso_date(start), _iso_date(end)


def draft_well_outage(
    text: str,
    *,
    base_constraints: Mapping[str, Any],
    dates: Sequence[str],
    available_wells: Collection[str],
) -> dict[str, Any]:
    """Return a validated constraints draft for one dated well outage.

    Accepted requests must name an outage action, exactly one known well, and
    one closed date range that exactly matches control dates in the active case.
    Unsupported or ambiguous wording raises :class:`CaseDraftError`.
    """

    if not _OUTAGE.search(text):
        raise CaseDraftError("only a well outage request is supported")
    wells = [match.group(1) for match in _WELL.finditer(text)]
    enumerated_wells = re.search(r"\b(?:и|and)\s+\d+\b", text, re.IGNORECASE)
    if len(wells) != 1 or enumerated_wells is not None:
        raise CaseDraftError("name exactly one well using “скважина 13” or “well 13”")
    well = wells[0]
    known_wells = {str(item) for item in available_wells}
    if well not in known_wells:
        raise CaseDraftError(f"well {well!r} is not present in the active case")

    start_date, end_date = _dates_from_request(text)
    date_steps = {str(value)[:10]: index for index, value in enumerate(dates)}
    if start_date not in date_steps or end_date not in date_steps:
        first = str(dates[0])[:10] if dates else "unavailable"
        last = str(dates[-1])[:10] if dates else "unavailable"
        raise CaseDraftError(
            f"both dates must match the active case control axis ({first} to {last})"
        )
    step_from, step_to = date_steps[start_date], date_steps[end_date]
    if step_from > step_to:
        raise CaseDraftError("the outage start date must not be after its end date")

    constraints = copy.deepcopy(dict(base_constraints))
    try:
        validated = constraints_from_json(constraints, n_intervals=len(dates))
    except ValueError as error:
        raise CaseDraftError(f"the active case constraints are invalid: {error}") from error
    outages = constraints.setdefault("well_outages", [])
    if not isinstance(outages, list):
        raise CaseDraftError("the active case outage list is invalid")
    for existing in validated.well_outages:
        if (
            existing.well == well
            and existing.control_step_from <= step_to
            and step_from <= existing.control_step_to
        ):
            raise CaseDraftError(
                f"well {well!r} already has an outage overlapping this date range"
            )

    addition = {
        "well": well,
        "control_step_from": step_from,
        "control_step_to": step_to,
    }
    updated_outages = [*outages, addition]
    constraints["well_outages"] = updated_outages
    try:
        constraints_from_json(constraints, n_intervals=len(dates))
    except ValueError as error:
        raise CaseDraftError(f"the proposed case is invalid: {error}") from error

    return {
        "operation": "add_well_outage",
        "well": well,
        "date_from": start_date,
        "date_to": end_date,
        "control_step_from": step_from,
        "control_step_to": step_to,
        "added": addition,
        "constraints": constraints,
    }


def draft_annual_rate_limit(
    text: str,
    *,
    base_constraints: Mapping[str, Any],
    dates: Sequence[str],
) -> dict[str, Any]:
    """Draft an annual injection or liquid limit in m³/day for a named year."""

    targets = [(section, pattern) for section, pattern in _LIMIT_TARGETS if pattern.search(text)]
    if len(targets) != 1:
        raise CaseDraftError(
            "name exactly one supported target: injection limit or liquid rate limit"
        )
    section = targets[0][0]
    amount_matches = list(_RATE_VALUE.finditer(text))
    year_matches = list(_YEAR.finditer(text))
    if len(amount_matches) != 1:
        raise CaseDraftError(
            "give exactly one non-negative rate with an explicit m³/day unit"
        )
    if len(year_matches) != 1:
        raise CaseDraftError("give exactly one forecast year, for example “за 2015 год”")
    amount = float(amount_matches[0].group(1).replace(",", "."))
    year = int(year_matches[0].group(1))
    available_years = {int(str(item)[:4]) for item in dates if str(item)[:4].isdigit()}
    if year not in available_years:
        first = min(available_years) if available_years else "unavailable"
        last = max(available_years) if available_years else "unavailable"
        raise CaseDraftError(f"year {year} is outside the active case horizon ({first} to {last})")

    constraints = copy.deepcopy(dict(base_constraints))
    try:
        constraints_from_json(constraints, n_intervals=len(dates))
    except ValueError as error:
        raise CaseDraftError(f"the active case constraints are invalid: {error}") from error
    year_map = constraints.setdefault(section, {})
    if not isinstance(year_map, dict):
        raise CaseDraftError(f"the active case {section} map is invalid")
    before = year_map.get(str(year))
    year_map[str(year)] = amount
    try:
        constraints_from_json(constraints, n_intervals=len(dates))
    except ValueError as error:
        raise CaseDraftError(f"the proposed case is invalid: {error}") from error
    return {
        "operation": "set_annual_rate_limit",
        "section": section,
        "year": year,
        "before": before,
        "after": amount,
        "unit": "m3/day",
        "constraints": constraints,
    }


def draft_case_request(
    text: str,
    *,
    base_constraints: Mapping[str, Any],
    dates: Sequence[str],
    available_wells: Collection[str],
) -> dict[str, Any]:
    """Dispatch to the strictly supported outage or annual-rate draft parser."""

    if _OUTAGE.search(text):
        return draft_well_outage(
            text,
            base_constraints=base_constraints,
            dates=dates,
            available_wells=available_wells,
        )
    return draft_annual_rate_limit(
        text,
        base_constraints=base_constraints,
        dates=dates,
    )
