from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Mapping

from backend.contexts.assistant.infrastructure.artifacts import (
    CLAIMED_NPV_FIELDS,
    MANIFEST_PROVENANCE_FIELDS,
    NOT_RECORDED,
    RunError,
    RunRecord,
)
from backend.contexts.assistant.application.tools.context import Card, ToolContext, ToolFailure
from backend.contexts.assistant.application.tools.labels import RUN_STATUS_LABELS, pick, title

NUMERIC_MANIFEST_FIELDS: tuple[str, ...] = (
    "predicted_npv",
    "verified_npv",
)
NO_SUBMISSION = "no-submission"
PROVENANCE_MANIFEST = "run-manifest"
PROVENANCE_SUBMISSION = "submission-bundle"


def _record(context: ToolContext, arguments: Mapping[str, Any]) -> RunRecord:
    requested = arguments.get("run_id")
    store = context.run_store()
    try:
        return store.read(str(requested) if requested is not None else None)
    except RunError as error:
        raise ToolFailure(str(error)) from error


def _value(record: RunRecord, name: str) -> Any:
    if not record.recorded(name):
        return None
    return record.manifest[name]


def _missing(record: RunRecord, names: tuple[str, ...]) -> list[str]:
    return [name for name in names if not record.recorded(name)]


def _violations(record: RunRecord) -> dict[str, Any]:
    validation = record.validation
    if validation is None:
        return {
            "recorded": False,
            "dynamic": None,
            "blocking": None,
            "failed_identities": None,
            "opm_status": None,
            "unavailable_reason": (
                "the run check is not recorded: there is no validation/result.json file, "
                "so the number of violations is unknown"
            ),
        }
    dynamic = validation.get("dynamic_violations")
    blocking = validation.get("blocking_dynamic_violations")
    identities = validation.get("failed_identities")
    return {
        "recorded": True,
        "dynamic": dynamic if isinstance(dynamic, int) else None,
        "blocking": blocking if isinstance(blocking, int) else None,
        "failed_identities": list(identities)
        if isinstance(identities, (list, tuple))
        else None,
        "opm_status": validation.get("opm_status"),
        "unavailable_reason": None,
    }


def _constraints(record: RunRecord) -> dict[str, Any]:
    report = record.constraints_report
    if report is None:
        return {
            "recorded": False,
            "checks": None,
            "unavailable_reason": (
                "there is no constraints report: the file "
                "validation/constraints_report.json is not recorded"
            ),
        }
    checks = report.get("checks")
    rows = list(checks) if isinstance(checks, (list, tuple)) else None
    recorded = rows is not None and len(rows) > 0
    unavailable_reason = report.get("unavailable_reason")
    if not recorded and not unavailable_reason:
        unavailable_reason = "the constraints report contains no check rows, so constraint coverage is unknown"
    return {
        "recorded": recorded,
        "checks": rows,
        "unavailable_reason": unavailable_reason,
    }


def _acceptance(record: RunRecord) -> dict[str, Any]:
    """Summarize only recorded run checks; missing evidence never becomes approval."""
    violations = _violations(record)
    constraints = _constraints(record)
    sound = _value(record, "sound")
    opm_status = violations["opm_status"]
    blocking = violations["blocking"]
    checks = constraints["checks"]
    if (
        sound is False
        or (isinstance(blocking, int) and blocking > 0)
        or (isinstance(opm_status, str) and opm_status != "OK")
    ):
        verdict = "rejected"
    elif (
        sound is True
        and blocking == 0
        and opm_status == "OK"
        and constraints["recorded"]
    ):
        verdict = "accepted_for_recorded_checks"
    else:
        verdict = "unknown"
    return {
        "verdict": verdict,
        "opm_status": opm_status,
        "sound": sound,
        "blocking_violations": blocking,
        "dynamic_violations": violations["dynamic"],
        "failed_identities": violations["failed_identities"],
        "checks_recorded": constraints["recorded"],
        "checks": checks,
        "unverified_reason": constraints["unavailable_reason"] if not constraints["recorded"] else None,
        "npv_sources": {
            "predicted": {"value": _value(record, "predicted_npv"), "source": "run manifest / surrogate prediction"},
            "verified": {"value": _value(record, "verified_npv"), "source": "run manifest / OPM verification"},
        },
        "scope_note": "Acceptance applies only to the recorded checks; absent checks are unknown.",
    }


def _violation_locations(record: RunRecord) -> dict[str, Any]:
    path = record.directory / "validation" / "violations.json"
    if not path.is_file():
        return {
            "recorded": False,
            "rows": [],
            "total": None,
            "truncated": False,
            "reason": "validation/violations.json is not recorded for this run",
        }
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        data = None
    if not isinstance(data, list):
        return {
            "recorded": False,
            "rows": [],
            "total": None,
            "truncated": False,
            "reason": "validation/violations.json is unreadable or has an invalid format",
        }
    rows: list[dict[str, Any]] = []
    for index, row in enumerate(data):
        if not isinstance(row, dict) or not isinstance(row.get("kind"), str) or not row["kind"]:
            return {
                "recorded": False, "rows": [], "total": None, "truncated": False,
                "reason": f"validation/violations.json row {index} has no violation kind",
            }
        for coordinate in ("control_step", "region"):
            value = row.get(coordinate)
            if value is not None and (isinstance(value, bool) or not isinstance(value, int) or value < 0):
                return {
                    "recorded": False, "rows": [], "total": None, "truncated": False,
                    "reason": f"validation/violations.json row {index} has an invalid {coordinate}",
                }
        well = row.get("well")
        value = row.get("value")
        detail = row.get("detail")
        blocking = row.get("blocking")
        if (well is not None and (not isinstance(well, str) or not well)
            or value is not None and (isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value))
            or detail is not None and not isinstance(detail, str)
            or not isinstance(blocking, bool)):
            return {
                "recorded": False, "rows": [], "total": None, "truncated": False,
                "reason": f"validation/violations.json row {index} has invalid location or violation fields",
            }
        rows.append({
            "kind": row["kind"],
            "control_step": row.get("control_step"),
            "well": well,
            "region": row.get("region"),
            "value": value,
            "detail": detail or "",
            "blocking": blocking,
        })
    return {
        "recorded": True,
        "rows": rows[:200],
        "total": len(rows),
        "truncated": len(rows) > 200,
        "reason": None,
    }


def _status_label(record: RunRecord, lang: str) -> str | None:
    status = record.manifest.get("status")
    if not isinstance(status, str):
        return None
    return pick(RUN_STATUS_LABELS, status, lang)


def run_status(context: ToolContext, arguments: Mapping[str, Any]) -> Card:
    record = _record(context, arguments)
    status = record.manifest.get("status")
    if not isinstance(status, str):
        raise ToolFailure(
            f"the manifest of run {record.run_id!r} carries no status: "
            f"{record.directory / 'manifest.json'}; the state of the calculation is unknown"
        )
    provenance_values = {
        name: _value(record, name) for name in MANIFEST_PROVENANCE_FIELDS
    }
    payload: dict[str, Any] = {
        "run_id": record.run_id,
        "status": status,
        "status_label": _status_label(record, context.lang),
        "schedule_hash": _value(record, "schedule_hash"),
        "predicted_npv": _value(record, "predicted_npv"),
        "verified_npv": _value(record, "verified_npv"),
        "sound": _value(record, "sound"),
        "search_strategy": _value(record, "search_strategy"),
        "provenance_fields": provenance_values,
        "not_recorded": _missing(
            record, NUMERIC_MANIFEST_FIELDS + MANIFEST_PROVENANCE_FIELDS
        ),
        "violations": _violations(record),
        "constraints": _constraints(record),
        "acceptance": _acceptance(record),
        "violation_locations": _violation_locations(record),
        "has_submission": record.submission is not None,
        "source": str(record.directory / "manifest.json"),
        "not_recorded_marker": NOT_RECORDED,
    }
    return Card(
        type="run-status",
        title=title("run_status", context.lang, run_id=record.run_id),
        payload=payload,
        provenance=PROVENANCE_MANIFEST,
    )


def submission_summary(context: ToolContext, arguments: Mapping[str, Any]) -> Card:
    record = _record(context, arguments)
    bundle = record.submission
    if bundle is None:
        payload: dict[str, Any] = {
            "run_id": record.run_id,
            "assembled": False,
            "code": NO_SUBMISSION,
            "status": record.manifest.get("status"),
            "claimed_npv_rub": None,
            "hashes": None,
            "schedule_include_present": record.schedule_include,
            "checks": None,
            "reason": (
                f"the submission package of run {record.run_id!r} is not assembled: there "
                f"is no {record.directory / 'submission' / 'claimed_npv.json'} file, "
                "so there is nothing to claim"
            ),
            "source": None,
        }
        return Card(
            type="submission",
            title=title("submission", context.lang, run_id=record.run_id),
            payload=payload,
            provenance=PROVENANCE_SUBMISSION,
        )
    claimed = bundle.get("claimed_npv_rub")
    if not isinstance(claimed, (int, float)) or isinstance(claimed, bool):
        raise ToolFailure(
            f"the submission package of run {record.run_id!r} carries no "
            f"claimed_npv_rub number, got {claimed!r}: a claimed NPV is not "
            "substituted for the recorded one"
        )
    hashes = {
        name: bundle.get(name)
        for name in CLAIMED_NPV_FIELDS
        if name != "claimed_npv_rub"
    }
    missing = sorted(name for name, value in hashes.items() if value is None)
    payload = {
        "run_id": record.run_id,
        "assembled": True,
        "code": None,
        "status": record.manifest.get("status"),
        "claimed_npv_rub": float(claimed),
        "hashes": hashes,
        "schedule_include_present": record.schedule_include,
        "checks": {
            "status_ready_to_submit": record.manifest.get("status")
            == "ready_to_submit",
            "schedule_include_present": record.schedule_include,
            "source_run_matches": bundle.get("source_run_id") == record.run_id,
            "schedule_hash_matches": (
                bundle.get("canonical_schedule_hash")
                == record.manifest.get("schedule_hash")
            ),
            "missing_fields": missing,
        },
        "reason": None,
        "source": str(record.directory / "submission" / "claimed_npv.json"),
    }
    return Card(
        type="submission",
        title=title("submission", context.lang, run_id=record.run_id),
        payload=payload,
        provenance=PROVENANCE_SUBMISSION,
    )
