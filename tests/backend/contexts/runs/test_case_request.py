from __future__ import annotations

import pytest

from backend.contexts.runs.application.case_request import (
    CaseDraftError,
    draft_annual_rate_limit,
    draft_case_request,
    draft_well_outage,
)


DATES = ("2010-01-01", "2010-02-01", "2010-03-01", "2010-04-01")
BASE = {
    "liquid_limits": {"2010": 120.0},
    "well_outages": [{"well": "8", "control_step_from": 0, "control_step_to": 1}],
    "infrastructure": {"external_water_m3_per_day": 0.0},
}


@pytest.mark.parametrize(
    ("text", "start", "end"),
    [
        ("Остановить скважину №13 с 01.02.2010 по 01.03.2010", 1, 2),
        ("shut in well 13 from 2010-02-01 to 2010-03-01", 1, 2),
    ],
)
def test_drafts_single_outage_and_preserves_existing_case(text: str, start: int, end: int) -> None:
    original = {**BASE, "well_outages": list(BASE["well_outages"])}

    draft = draft_well_outage(
        text,
        base_constraints=original,
        dates=DATES,
        available_wells={"8", "13"},
    )

    assert draft["operation"] == "add_well_outage"
    assert draft["date_from"] == DATES[start]
    assert draft["date_to"] == DATES[end]
    assert draft["control_step_from"] == start
    assert draft["control_step_to"] == end
    assert draft["constraints"]["well_outages"] == [
        *BASE["well_outages"],
        {"well": "13", "control_step_from": start, "control_step_to": end},
    ]
    assert original == BASE


@pytest.mark.parametrize(
    ("text", "wells", "dates", "message"),
    [
        ("Скважина 13 простаивает с 01.02.2010 по 01.03.2010", {"13"}, DATES, "outage request"),
        ("Остановить скважину 14 с 01.02.2010 по 01.03.2010", {"13"}, DATES, "not present"),
        ("Остановить скважину 13 с 01.05.2010 по 01.06.2010", {"13"}, DATES, "control axis"),
        ("Остановить скважину 13 с 01.03.2010 по 01.02.2010", {"13"}, DATES, "must not be after"),
        ("Остановить скважину 13 с 31.02.2010 по 01.03.2010", {"13"}, DATES, "valid calendar date"),
        ("Остановить скважины 13 и 8 с 01.02.2010 по 01.03.2010", {"13", "8"}, DATES, "exactly one well"),
        ("Установить лимит жидкости 100", {"13"}, DATES, "only a well outage"),
    ],
)
def test_rejects_unsupported_or_ambiguous_request(
    text: str, wells: set[str], dates: tuple[str, ...], message: str
) -> None:
    with pytest.raises(CaseDraftError, match=message):
        draft_well_outage(
            text,
            base_constraints=BASE,
            dates=dates,
            available_wells=wells,
        )


def test_rejects_overlapping_existing_outage() -> None:
    with pytest.raises(CaseDraftError, match="already has an outage overlapping"):
        draft_well_outage(
            "Остановить скважину 8 с 01.02.2010 по 01.03.2010",
            base_constraints=BASE,
            dates=DATES,
            available_wells={"8"},
        )


def test_rejects_multiple_date_ranges() -> None:
    with pytest.raises(CaseDraftError, match="exactly one date range"):
        draft_well_outage(
            "Остановить скважину 13 с 01.02.2010 по 01.03.2010, а потом с 01.04.2010 по 01.05.2010",
            base_constraints=BASE,
            dates=DATES,
            available_wells={"13"},
        )


@pytest.mark.parametrize(
    ("text", "section", "amount"),
    [
        ("Установить лимит закачки 100 м³/сут за 2010 год", "injection_limits", 100.0),
        ("set liquid rate limit to 125.5 m3/day for 2010", "liquid_limits", 125.5),
        ("лимит дебита жидкости 75,25 м3/сут в 2010 году", "liquid_limits", 75.25),
    ],
)
def test_drafts_annual_rate_limit(text: str, section: str, amount: float) -> None:
    draft = draft_case_request(
        text,
        base_constraints=BASE,
        dates=DATES,
        available_wells={"8", "13"},
    )

    assert draft["operation"] == "set_annual_rate_limit"
    assert draft["section"] == section
    assert draft["year"] == 2010
    assert draft["before"] == (120.0 if section == "liquid_limits" else None)
    assert draft["after"] == amount
    assert draft["unit"] == "m3/day"
    assert draft["constraints"][section]["2010"] == amount
    assert draft["constraints"]["well_outages"] == BASE["well_outages"]


def test_rate_limit_draft_reports_previous_value_when_replacing_same_year() -> None:
    draft = draft_annual_rate_limit(
        "Установить лимит закачки 100 м3/сут за 2010 год",
        base_constraints={**BASE, "injection_limits": {"2010": 80.0}},
        dates=DATES,
    )

    assert draft["before"] == 80.0
    assert draft["after"] == 100.0


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("лимит закачки 100 в 2010 году", "explicit m³/day unit"),
        ("лимит закачки -100 м3/сут за 2010 год", "explicit m³/day unit"),
        ("лимит жидкости 100 м3/сут", "exactly one forecast year"),
        ("лимит закачки 100 бар за 2010 год", "explicit m³/day unit"),
        ("лимит закачки 100 м3/сут за 2030 год", "outside the active case horizon"),
        ("лимит закачки и лимит жидкости 100 м3/сут за 2010 год", "exactly one supported target"),
    ],
)
def test_rejects_unsupported_rate_limit_requests(text: str, message: str) -> None:
    with pytest.raises(CaseDraftError, match=message):
        draft_case_request(
            text,
            base_constraints=BASE,
            dates=DATES,
            available_wells={"8", "13"},
        )
