from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import quote

from backend.contexts.assistant.infrastructure.artifacts import MANIFEST_FILE, RunError, RunRecord
from backend.contexts.assistant.application.tools.context import Card, ToolContext, ToolFailure
from backend.contexts.assistant.application.tools.runs import _acceptance
from backend.shared.settings import Settings
from backend.shared.paths import repository_root

WEB_RUNS_ENV_VAR = "AIOS_JARVIS_WEB_RUNS"
DEFAULT_LIMIT = 6
MAX_LIMIT = 10
PROVENANCE = "runs"
NO_RUNS = "no-runs"
NO_COMPARISON = "no-comparison"
COMPARISON_FILE = "comparison.json"
PHYSICS_PREFIX = "physics"
VALIDATION_DIR = "validation"
TITLES: Mapping[str, Mapping[str, str]] = {
    "list": {"ru": "Прогоны расчёта", "en": "Calculation runs"},
    "detail": {"ru": "Прогон {run_id}", "en": "Run {run_id}"},
    "compare": {"ru": "{a} против {b}", "en": "{a} versus {b}"},
    "physics": {"ru": "Физика прогона {run_id}", "en": "Physics of run {run_id}"},
}


def _title(key: str, lang: str, **values: object) -> str:
    entry = TITLES.get(key, {})
    return entry.get(lang, entry.get("ru", key)).format(**values)


def _repository_root() -> Path:
    return repository_root(Path.cwd())


def _web_runs_root(settings: Settings | None = None) -> Path:
    resolved = Settings.from_env() if settings is None else settings
    if resolved.jarvis_web_runs is not None:
        return resolved.jarvis_web_runs
    base = resolved.out_root if resolved.raw.get("AIOS_OUT_DIR") else _repository_root() / "out"
    return base / "web-runs"


@dataclass(frozen=True, slots=True)
class Located:
    run_id: str
    directory: Path
    manifest: Mapping[str, Any]
    mtime: float


def _read_json(path: Path) -> Mapping[str, Any] | None:
    if not path.is_file():
        return None
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    return loaded if isinstance(loaded, dict) else None


def _scenario_registry() -> tuple[Mapping[str, Any], ...]:
    payload = _read_json(_repository_root() / "artifacts" / "jarvis-scenario-registry.json")
    if payload is None or payload.get("schema_version") != 1:
        return ()
    entries = payload.get("entries")
    if not isinstance(entries, list):
        return ()
    return tuple(row for row in entries if isinstance(row, Mapping))


def _registered_row(entry: Mapping[str, Any]) -> dict[str, Any]:
    reasons = entry.get("generation_reasons")
    available = reasons.get("available") if isinstance(reasons, Mapping) else None
    return {
        "run_id": entry.get("run_id"),
        "ts": "",
        "status": entry.get("status"),
        "predicted_npv": None,
        "verified_npv": entry.get("verified_npv_rub"),
        "sound": entry.get("sound"),
        "schedule_hash": entry.get("schedule_hash"),
        "strategy": None,
        "seed": None,
        "opm_status": entry.get("opm_status"),
        "scenario_role": entry.get("role"),
        "generation_journal_available": available is True,
        "generation_journal_present": available is True,
        "generation_reasons_status": "recorded-and-indexed" if available is True else "unavailable",
        "run_manifest_available": (entry.get("run_manifest") or {}).get("available") is True,
        "label": entry.get("label"),
        "availability": entry,
    }


def _scan(root: Path, context: ToolContext | None = None) -> list[Located]:
    if not root.is_dir():
        return []
    found: list[Located] = []
    for position, entry in enumerate(sorted(root.iterdir())):
        if context is not None and position % 32 == 0:
            context.check_cancelled()
        if not entry.is_dir():
            continue
        path = entry / MANIFEST_FILE
        manifest = _read_json(path)
        if manifest is None:
            continue
        found.append(
            Located(
                run_id=entry.name,
                directory=entry,
                manifest=manifest,
                mtime=path.stat().st_mtime,
            )
        )
    return found


def _roots(context: ToolContext) -> list[Path]:
    collected: list[Path] = []
    try:
        collected.append(context.run_store().root)
    except ToolFailure:
        pass
    web = _web_runs_root()
    if web not in collected:
        collected.append(web)
    return collected


def _located(context: ToolContext) -> list[Located]:
    found: list[Located] = []
    seen: set[str] = set()
    for root in _roots(context):
        context.check_cancelled()
        for item in _scan(root, context):
            if item.run_id in seen:
                continue
            seen.add(item.run_id)
            found.append(item)
    found.sort(key=lambda item: (-item.mtime, item.run_id))
    return found


def _stamp(value: float) -> str:
    return (
        datetime.fromtimestamp(value, tz=timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _find(context: ToolContext, run_id: str | None) -> Located:
    items = _located(context)
    if not items:
        roots = ", ".join(str(root) for root in _roots(context))
        raise ToolFailure(
            f"{NO_RUNS}: no run with a manifest was found in the directories "
            f"{roots}; no calculation has been made yet, and its result cannot be invented"
        )
    if run_id is None:
        return items[0]
    for item in items:
        if item.run_id == run_id:
            return item
    known = ", ".join(item.run_id for item in items[:MAX_LIMIT])
    raise ToolFailure(
        f"run {run_id!r} is in none of the run directories: known runs "
        f"are {known}"
    )


def _row(item: Located) -> dict[str, Any]:
    validation = _read_json(item.directory / VALIDATION_DIR / "result.json") or {}
    provenance = _read_json(item.directory / "provenance.json") or {}
    origin = _read_json(item.directory / "inputs" / "origin.json") or {}
    if origin.get("is_final_submission") is True:
        scenario_role = "submitted-plan"
    elif origin.get("kind") == "fresh-opm-repeat-of-archived-schedule":
        scenario_role = "historical-repeat"
    elif origin.get("kind") == "single-policy-pass-on-real-baseline-feedback":
        scenario_role = "diagnostic-policy-run"
    else:
        scenario_role = "unclassified"
    journal_available = (item.directory / "decision-evidence-index.json").is_file()
    generation_journal_present = (
        (item.directory / "inputs" / "decision-journal.jsonl").is_file()
        or (item.directory / "well-explanations.json").is_file()
    )
    return {
        "run_id": item.run_id,
        "ts": _stamp(item.mtime),
        "status": item.manifest.get("status"),
        "predicted_npv": item.manifest.get("predicted_npv"),
        "verified_npv": item.manifest.get("verified_npv"),
        "sound": item.manifest.get("sound"),
        "schedule_hash": item.manifest.get("schedule_hash"),
        "strategy": item.manifest.get("search_strategy")
        or provenance.get("search_strategy"),
        "seed": item.manifest.get("seed") or provenance.get("seed"),
        "opm_status": validation.get("opm_status"),
        "scenario_role": scenario_role,
        "origin": origin or None,
        "generation_journal_available": journal_available,
        "generation_journal_present": generation_journal_present,
        "generation_reasons_status": (
            "recorded-and-indexed" if journal_available
            else "recorded-not-indexed" if generation_journal_present
            else "unavailable"
        ),
        "source": str(item.directory),
    }


def run_history(context: ToolContext, arguments: Mapping[str, Any]) -> Card:
    requested = arguments.get("limit")
    limit = int(requested) if isinstance(requested, (int, float)) else DEFAULT_LIMIT
    limit = max(1, min(limit, MAX_LIMIT))
    status = arguments.get("status")
    items = _located(context)
    registry = _scenario_registry()
    if not items and not registry:
        roots = ", ".join(str(root) for root in _roots(context))
        raise ToolFailure(
            f"{NO_RUNS}: no run with a manifest was found in the directories "
            f"{roots}; there is no list of runs"
        )
    rows = [_row(item) for item in items]
    present = {row["run_id"] for row in rows}
    rows.extend(_registered_row(entry) for entry in registry if entry.get("run_id") not in present)
    if status is not None:
        wanted = str(status)
        statuses = sorted({str(row["status"]) for row in rows if row["status"] is not None})
        matched = [row for row in rows if row["status"] == wanted]
        if not matched:
            raise ToolFailure(
                f"there are no runs with status {wanted!r}: the statuses present "
                f"are {', '.join(statuses)}"
            )
        rows = matched
    payload = {
        "rows": rows[:limit],
        "total": len(rows),
        "status": str(status) if status is not None else None,
        "roots": [str(root) for root in _roots(context)],
    }
    return Card(
        type="run-list",
        title=_title("list", context.lang),
        payload=payload,
        provenance=PROVENANCE,
    )


def _physics_files(directory: Path) -> list[Path]:
    folder = directory / VALIDATION_DIR
    if not folder.is_dir():
        return []
    return sorted(
        path
        for path in folder.glob("*.json")
        if path.stem.startswith(PHYSICS_PREFIX)
    )


def _physics(directory: Path) -> dict[str, Any]:
    files = _physics_files(directory)
    if not files:
        return {
            "recorded": False,
            "admissible": None,
            "checks": [],
            "blocking": None,
            "warnings": None,
            "reason": (
                "there is no physics report: the directory "
                f"{directory / VALIDATION_DIR} holds no physics*.json file, so "
                "the admissibility of the response is unknown"
            ),
            "source": None,
        }
    loaded = _read_json(files[0]) or {}
    raw_checks = loaded.get("checks") or loaded.get("invariants") or ()
    checks: list[dict[str, Any]] = []
    for entry in raw_checks:
        if not isinstance(entry, Mapping):
            continue
        checks.append(
            {
                "id": entry.get("id") or entry.get("kind") or entry.get("name"),
                "status": entry.get("status") or entry.get("severity"),
                "detail": entry.get("detail") or entry.get("message"),
            }
        )
    blocking = sum(1 for row in checks if row["status"] == "blocking")
    warnings = sum(1 for row in checks if row["status"] == "warning")
    return {
        "recorded": True,
        "admissible": loaded.get("admissible"),
        "checks": checks,
        "blocking": blocking,
        "warnings": warnings,
        "reason": None,
        "source": str(files[0]),
    }


def _detail(context: ToolContext, item: Located) -> dict[str, Any]:
    validation = _read_json(item.directory / VALIDATION_DIR / "result.json")
    constraints = _read_json(
        item.directory / VALIDATION_DIR / "constraints_report.json"
    )
    submission = _read_json(item.directory / "submission" / "claimed_npv.json")
    provenance = _read_json(item.directory / "provenance.json") or {}
    violations: list[dict[str, Any]] = []
    if validation is not None:
        for name in validation.get("failed_identities", ()) or ():
            violations.append({"kind": "identity", "detail": str(name)})
        dynamic = validation.get("dynamic_violations")
        blocking = validation.get("blocking_dynamic_violations")
        if isinstance(dynamic, int):
            violations.append({"kind": "dynamic-violations", "detail": f"{dynamic} total; {blocking} blocking"})
    record = RunRecord(
        run_id=item.run_id, directory=item.directory, manifest=item.manifest,
        validation=validation, constraints_report=constraints, submission=submission,
        schedule_include=(item.directory / "submission" / "well_schedule.inc").is_file(),
    )
    return {
        "run_id": item.run_id,
        "ts": _stamp(item.mtime),
        "status": item.manifest.get("status"),
        "predicted_npv": item.manifest.get("predicted_npv"),
        "verified_npv": item.manifest.get("verified_npv"),
        "sound": item.manifest.get("sound"),
        "schedule_hash": item.manifest.get("schedule_hash"),
        "provenance": dict(provenance),
        "validation": dict(validation) if validation is not None else None,
        "constraints_report": dict(constraints) if constraints is not None else None,
        "claimed_npv_rub": (
            submission.get("claimed_npv_rub") if submission is not None else None
        ),
        "has_submission": submission is not None,
        "violations": violations,
        "physics": _physics(item.directory),
        "acceptance": _acceptance(record),
        "source": str(item.directory / MANIFEST_FILE),
    }


def _conclusion_markdown(item: Located, lang: str) -> str:
    validation = _read_json(item.directory / VALIDATION_DIR / "result.json")
    constraints = _read_json(item.directory / VALIDATION_DIR / "constraints_report.json")
    physics = _physics(item.directory)
    manifest = item.manifest
    sound = manifest.get("sound")
    blocking = validation.get("blocking_dynamic_violations") if validation else None
    checks = constraints.get("checks") if constraints else None
    if sound is False or (isinstance(blocking, int) and blocking > 0) or physics.get("admissible") is False:
        verdict_ru, verdict_en = "Отклонён. План не рекомендован к применению.", "Rejected. The plan is not recommended for use."
    elif sound is True and physics.get("admissible") is True and isinstance(checks, list) and len(checks) > 0:
        verdict_ru, verdict_en = "Проходит записанные проверки; это заключение ограничено указанным составом проверок.", "Passes the recorded checks; this conclusion is limited to the checks listed here."
    else:
        verdict_ru, verdict_en = "Допуск не установлен: часть проверок отсутствует или не записана.", "Eligibility is unknown: some checks are missing or were not recorded."
    run_url = quote(item.run_id, safe="")
    sources = [
        ("manifest.json", "manifest"),
        ("validation/result.json", "validation"),
        ("validation/constraints_report.json", "constraints"),
        ("validation/physics*.json", "physics"),
        ("economics/result.json", "economics"),
        ("economics/npv-table.json", "npv-table"),
    ]
    if (item.directory / "submission" / "claimed_npv.json").is_file():
        sources.append(("submission/claimed_npv.json", "submission"))
    recorded_sources = [
        f"- [{label}](/api/jarvis/run-artifacts/{run_url}/{key})"
        for label, key in sources
        if {
            "manifest": item.directory / "manifest.json",
            "validation": item.directory / "validation" / "result.json",
            "constraints": item.directory / "validation" / "constraints_report.json",
            "economics": item.directory / "economics" / "result.json",
            "npv-table": item.directory / "economics" / "npv-table.json",
            "submission": item.directory / "submission" / "claimed_npv.json",
            "physics": next(iter(sorted((item.directory / VALIDATION_DIR).glob("physics*.json"))), item.directory / "validation" / "physics-report.json"),
        }[key].is_file()
    ]
    predicted = manifest.get("predicted_npv")
    verified = manifest.get("verified_npv")
    status = manifest.get("status", "not-recorded")
    provenance = _read_json(item.directory / "provenance.json") or {}
    origin = _read_json(item.directory / "inputs" / "origin.json") or {}
    strategy = manifest.get("search_strategy") or provenance.get("search_strategy")
    seed = manifest.get("seed") or provenance.get("seed")
    recorded_origin = origin.get("kind") or origin.get("reason") or origin.get("description")
    opm = validation.get("opm_status") if validation else None
    dynamic = validation.get("dynamic_violations") if validation else None
    blocking_text = str(blocking) if isinstance(blocking, int) else "not recorded"
    check_lines: list[str] = []
    if isinstance(checks, list):
        for check in checks:
            if not isinstance(check, Mapping):
                continue
            check_lines.append(
                f"- {check.get('constraint', 'check')}: {check.get('status', 'unknown')}; "
                f"violations={check.get('n_violations', 'not recorded')}; blocking={check.get('blocking', 'not recorded')}; "
                f"enforcement={check.get('enforcement', 'not recorded')}; detail={check.get('detail', 'not recorded')}"
            )
    else:
        reason = constraints.get("unavailable_reason") if constraints else None
        check_lines.append(f"- Not recorded: {reason or 'constraints report is missing'}")
    physics_lines = [
        f"- Admissible: {physics.get('admissible') if physics.get('admissible') is not None else 'not recorded'}; "
        f"blocking checks: {physics.get('blocking') if physics.get('blocking') is not None else 'not recorded'}; "
        f"warnings: {physics.get('warnings') if physics.get('warnings') is not None else 'not recorded'}."
    ]
    if physics.get("recorded") is True:
        physics_lines.extend(
            f"- {row.get('id')}: {row.get('status') or 'unknown'}; {row.get('detail') or 'no detail recorded'}"
            for row in physics.get("checks", ())
            if isinstance(row, Mapping)
        )
    elif physics.get("reason"):
        physics_lines.append(f"- {physics['reason']}")
    if lang == "ru":
        return "\n".join([
            f"# Инженерное заключение: прогон {item.run_id}", "",
            "## План", f"- Статус: `{status}`", f"- Хеш расписания: `{manifest.get('schedule_hash') or 'не записан'}`",
            f"- Стратегия: `{strategy or 'не записана'}`; seed: `{seed if seed is not None else 'не записан'}`.",
            f"- Происхождение/основание выбора: {recorded_origin or 'не записано'}.", "",
            "## Расчёт и допуск", f"- OPM: `{opm or 'не записан'}`; sound: `{sound if sound is not None else 'не записан'}`.",
            f"- Динамические нарушения: {dynamic if isinstance(dynamic, int) else 'не записаны'}; блокирующие: {blocking_text}.",
            f"- Прогноз суррогата: {predicted if predicted is not None else 'не записан'}.",
            f"- ЧДД после проверки OPM: {verified if verified is not None else 'не записан'}.",
            f"- Вывод: **{verdict_ru}**", "", "## Физические проверки", *physics_lines, "",
            "## Проверки ограничений", *check_lines, "",
            "## Источники", *(recorded_sources or ["- Источники прогона не найдены."]), ""
        ])
    return "\n".join([
        f"# Engineering conclusion: run {item.run_id}", "",
        "## Plan", f"- Status: `{status}`", f"- Schedule hash: `{manifest.get('schedule_hash') or 'not recorded'}`",
        f"- Strategy: `{strategy or 'not recorded'}`; seed: `{seed if seed is not None else 'not recorded'}`.",
        f"- Origin/selection basis: {recorded_origin or 'not recorded'}.", "",
        "## Calculation and eligibility", f"- OPM: `{opm or 'not recorded'}`; sound: `{sound if sound is not None else 'not recorded'}`.",
        f"- Dynamic violations: {dynamic if isinstance(dynamic, int) else 'not recorded'}; blocking: {blocking_text}.",
        f"- Surrogate forecast NPV: {predicted if predicted is not None else 'not recorded'}.",
        f"- OPM-verified NPV: {verified if verified is not None else 'not recorded'}.",
        f"- Conclusion: **{verdict_en}**", "", "## Physics checks", *physics_lines, "",
        "## Constraint checks", *check_lines, "",
        "## Sources", *(recorded_sources or ["- No run sources were found."]), ""
    ])


def _registered_conclusion_markdown(entry: Mapping[str, Any], lang: str) -> str:
    """Summarize registry evidence without implying a missing run manifest exists."""
    bundle = entry.get("bundle") if isinstance(entry.get("bundle"), Mapping) else {}
    checks = entry.get("cross_checks") if isinstance(entry.get("cross_checks"), Mapping) else {}
    run_id = str(entry.get("run_id") or "unknown")
    label = str(entry.get("label") or run_id)
    status = str(entry.get("status") or "not recorded")
    opm = str(entry.get("opm_status") or "not recorded")
    sound = entry.get("sound")
    verified_npv = entry.get("verified_npv_rub")
    dynamic = entry.get("dynamic_violations")
    blocking = entry.get("blocking_dynamic_violations")
    schedule_hash = entry.get("schedule_hash") or bundle.get("schedule_hash") or "not recorded"
    violations_text = (
        f"{dynamic} total; {blocking} blocking"
        if isinstance(dynamic, int) and isinstance(blocking, int)
        else "not recorded"
    )
    npv_text = f"{verified_npv} RUB" if isinstance(verified_npv, (int, float)) else "not recorded"
    if lang == "ru":
        verdict = (
            "Проверенный результат OPM зарегистрирован; допуск к применению не установлен без исходного manifest и полного отчёта ограничений."
            if status == "verified" and opm == "OK"
            else "Данных реестра недостаточно, чтобы установить допуск к применению."
        )
        return "\n".join([
            f"# Инженерное заключение: {label}", "",
            "> Ограниченное заключение по реестру: оригинальный run manifest отсутствует. Причины генерации доступны только в объёме, указанном ниже.", "",
            "## Зарегистрированные результаты",
            f"- Статус реестра: `{status}`; OPM: `{opm}`; sound: `{sound if sound is not None else 'не записан'}`.",
            f"- ЧДД, проверенный OPM: {npv_text}; прогноз суррогата: не записан в реестре.",
            f"- Хеш расписания: `{schedule_hash}`.", f"- Динамические нарушения: {violations_text}.",
            f"- Перекрёстная проверка кандидата: `{checks.get('candidate_018_reference_parity', 'не записана')}`; совпадение хеша расписания: `{checks.get('champion_schedule_hash_matches', 'не записано')}`; совпадение ЧДД: `{checks.get('champion_npv_matches', 'не записано')}`.", "",
            "## Вывод", verdict, "",
            "Причины генерации, полный manifest, проверки ограничений и годовая структура экономики не восстановлены и этим заключением не подтверждаются.", "",
            "## Источники",
            "- `artifacts/jarvis-scenario-registry.json` (запись реестра и указанные в ней перекрёстные проверки).",
            f"- `{bundle.get('path', 'пакет сценария не указан')}/{bundle.get('schedule_file', 'well_schedule.inc')}` (план; хеш `{schedule_hash}`).",
            f"- `{bundle.get('path', 'пакет сценария не указан')}/{bundle.get('claimed_file', 'claimed_npv.json')}` (заявленные данные пакета; не заменяют проверенный расчёт).", "",
        ])
    verdict = (
        "An OPM-verified result is recorded; eligibility for use is not established without the original manifest and complete constraints report."
        if status == "verified" and opm == "OK"
        else "The registry does not contain enough evidence to establish eligibility for use."
    )
    return "\n".join([
        f"# Engineering conclusion: {label}", "",
        "> Limited registry-based conclusion: the original run manifest is missing. Generation reasons are available only to the extent listed below.", "",
        "## Recorded results", f"- Registry status: `{status}`; OPM: `{opm}`; sound: `{sound if sound is not None else 'not recorded'}`.",
        f"- OPM-verified NPV: {npv_text}; surrogate forecast: not recorded in the registry.",
        f"- Schedule hash: `{schedule_hash}`.", f"- Dynamic violations: {violations_text}.",
        f"- Candidate cross-check: `{checks.get('candidate_018_reference_parity', 'not recorded')}`; schedule hash match: `{checks.get('champion_schedule_hash_matches', 'not recorded')}`; NPV match: `{checks.get('champion_npv_matches', 'not recorded')}`.", "",
        "## Conclusion", verdict, "",
        "Generation reasons, the complete manifest, constraint checks, and annual economics were not recovered and are not asserted here.", "",
        "## Sources", "- `artifacts/jarvis-scenario-registry.json` (registry entry and its recorded cross-checks).",
        f"- `{bundle.get('path', 'scenario bundle not recorded')}/{bundle.get('schedule_file', 'well_schedule.inc')}` (schedule; hash `{schedule_hash}`).",
        f"- `{bundle.get('path', 'scenario bundle not recorded')}/{bundle.get('claimed_file', 'claimed_npv.json')}` (bundle claim; does not replace verified calculation).", "",
    ])


def run_detail(context: ToolContext, arguments: Mapping[str, Any]) -> Card:
    requested = arguments.get("run_id")
    requested_id = str(requested) if requested is not None else None
    registered = next(
        (entry for entry in _scenario_registry() if entry.get("run_id") == requested_id),
        None,
    )
    has_recorded_manifest = requested_id is not None and any(
        item.run_id == requested_id for item in _located(context)
    )
    if registered is not None and not has_recorded_manifest and not (registered.get("run_manifest") or {}).get("available"):
        violations = registered.get("dynamic_violations")
        blocking = registered.get("blocking_dynamic_violations")
        role = str(registered.get("role") or "registered-scenario")
        availability_note = (
            "Загружен проверенный пакет и результаты проверки; исходный run manifest и журнал генерации локально отсутствуют."
            if context.lang == "ru"
            else "The verified bundle and check results are available; the original run manifest and generation journal are not present locally."
        )
        payload = {
            "run_id": registered.get("run_id"),
            "ts": "",
            "status": registered.get("status"),
            "predicted_npv": None,
            "verified_npv": registered.get("verified_npv_rub"),
            "sound": registered.get("sound"),
            "schedule_hash": registered.get("schedule_hash"),
            "claimed_npv_rub": (registered.get("bundle") or {}).get("claimed_npv_rub", registered.get("verified_npv_rub")),
            "has_submission": True,
            "violations": ([{"kind": "dynamic-violations", "detail": f"{violations} total; {blocking} blocking"}] if isinstance(violations, int) else []),
            "physics": None,
            "scenario_role": role,
            "generation_reasons_status": "unavailable",
            "run_manifest_available": False,
            "availability_note": availability_note,
            "bundle": registered.get("bundle"),
            "run_manifest": registered.get("run_manifest"),
            "generation_reasons": registered.get("generation_reasons"),
            "response_artifact": registered.get("response_artifact"),
            "cross_checks": registered.get("cross_checks"),
            "source": str(_repository_root() / "artifacts" / "jarvis-scenario-registry.json"),
            "conclusion_markdown": _registered_conclusion_markdown(registered, context.lang),
        }
        return Card(
            type="run",
            title=_title("detail", context.lang, run_id=str(registered.get("run_id"))),
            payload=payload,
            provenance="scenario-registry",
        )
    item = _find(context, requested_id)
    detail = _detail(context, item)
    detail["conclusion_markdown"] = _conclusion_markdown(item, context.lang)
    return Card(
        type="run",
        title=_title("detail", context.lang, run_id=item.run_id),
        payload=detail,
        provenance=PROVENANCE,
    )


def physics_report(context: ToolContext, arguments: Mapping[str, Any]) -> Card:
    requested = arguments.get("run_id")
    item = _find(context, str(requested) if requested is not None else None)
    report = _physics(item.directory)
    if not report["recorded"]:
        raise ToolFailure(
            f"{report['reason']} (run {item.run_id})"
        )
    payload = {
        "run_id": item.run_id,
        "admissible": report["admissible"],
        "checks": report["checks"],
        "blocking": report["blocking"],
        "warnings": report["warnings"],
        "source": report["source"],
    }
    return Card(
        type="physics",
        title=_title("physics", context.lang, run_id=item.run_id),
        payload=payload,
        provenance=PROVENANCE,
    )


def _side(item: Located, context: ToolContext) -> dict[str, Any]:
    detail = _detail(context, item)
    physics = detail["physics"]
    npv_basis = (
        "verified" if detail["verified_npv"] is not None
        else "predicted" if detail["predicted_npv"] is not None
        else None
    )
    return {
        "id": item.run_id,
        "npv": detail["verified_npv"]
        if detail["verified_npv"] is not None
        else detail["predicted_npv"],
        "npv_basis": npv_basis,
        "predicted_npv": detail["predicted_npv"],
        "verified_npv": detail["verified_npv"],
        "status": {
            "status": detail["status"],
            "sound": detail["sound"],
            "has_submission": detail["has_submission"],
            "opm_status": (detail["validation"] or {}).get("opm_status"),
            "physics_admissible": physics["admissible"],
        },
        "constraints": {
            "recorded": detail["constraints_report"] is not None,
            "checks": (detail["constraints_report"] or {}).get("checks"),
            "dynamic_violations": (detail["validation"] or {}).get(
                "dynamic_violations"
            ),
            "blocking_dynamic_violations": (detail["validation"] or {}).get(
                "blocking_dynamic_violations"
            ),
        },
    }


def _comparison_signature(item: Located) -> dict[str, Any]:
    manifest = item.manifest
    economics = _read_json(item.directory / "economics" / "result.json") or {}
    # A missing signature field means the pair cannot be certified comparable.
    return {
        "case": manifest.get("case_id"),
        "horizon": manifest.get("horizon"),
        "constraints": manifest.get("constraints_hash"),
        "normatives": manifest.get("normatives_sha256"),
        "economics_config": economics.get("economics_config_hash"),
        "methodology": economics.get("methodology_version_hash"),
        "model": manifest.get("model_version"),
        "opm_image": manifest.get("opm_image"),
    }


def _comparability(left: Located, right: Located, lang: str) -> dict[str, Any]:
    a = _comparison_signature(left)
    b = _comparison_signature(right)
    missing = [key for key in a if a[key] is None or b[key] is None]
    mismatched = [key for key in a if a[key] is not None and b[key] is not None and a[key] != b[key]]
    status = "incomparable" if mismatched else "unverified" if missing else "comparable"
    if lang == "ru":
        note = (
            f"Условия не совпадают по полям: {', '.join(mismatched)}."
            if mismatched
            else f"Сопоставимость не подтверждена: нет данных для полей {', '.join(missing)}."
            if missing
            else "Проверенные условия совпадают; разница ЧДД всё равно не доказывает причинный эффект."
        )
        note += " Разница ЧДД — арифметическая разница результатов, не причинный вклад отдельного действия."
    else:
        note = (
            f"Conditions differ on: {', '.join(mismatched)}."
            if mismatched
            else f"Comparability is unverified; data is missing for: {', '.join(missing)}."
            if missing
            else "Recorded conditions match; the NPV difference still does not establish a causal effect."
        )
        note += " The NPV delta is arithmetic, not a causal attribution to an individual action."
    return {
        "status": status,
        "checked_fields": list(a),
        "missing_fields": missing,
        "mismatched_fields": mismatched,
        "a": a,
        "b": b,
        "note": note,
    }


def _economic_breakdown(left: Located, right: Located) -> dict[str, Any]:
    tables = [
        _read_json(item.directory / "economics" / "npv-table.json")
        for item in (left, right)
    ]
    if not all(isinstance(table, Mapping) for table in tables):
        return {"recorded": False, "deltas": None, "reason": "one or both runs have no recorded economics/npv-table.json"}
    totals: list[dict[str, float]] = []
    for table in tables:
        rows = table.get("by_year")
        if not isinstance(rows, Mapping) or not rows:
            return {"recorded": False, "deltas": None, "reason": "the recorded NPV table has no annual line items"}
        aggregate: dict[str, float] = {}
        for row in rows.values():
            if not isinstance(row, Mapping):
                continue
            for key, value in row.items():
                if isinstance(value, (int, float)) and not isinstance(value, bool):
                    aggregate[key] = aggregate.get(key, 0.0) + float(value)
        totals.append(aggregate)
    shared = sorted(set(totals[0]) & set(totals[1]))
    return {
        "recorded": True,
        "deltas_b_minus_a": {key: totals[1][key] - totals[0][key] for key in shared},
        "a_totals": totals[0],
        "b_totals": totals[1],
        "source_a": str(left.directory / "economics" / "npv-table.json"),
        "source_b": str(right.directory / "economics" / "npv-table.json"),
        "reason": None,
    }


def _production_injection_breakdown(
    left: Located, right: Located, context: ToolContext | None = None
) -> dict[str, Any]:
    def response(item: Located) -> tuple[Mapping[str, Any] | None, Path]:
        schedule_hash = item.manifest.get("schedule_hash")
        path = item.directory / "observation" / str(schedule_hash) / "response.json"
        return _read_json(path), path

    responses = [response(item) for item in (left, right)]
    if not all(isinstance(payload, Mapping) for payload, _ in responses):
        return {
            "recorded": False,
            "reason": "one or both runs have no observation/<schedule_hash>/response.json",
            "source_a": str(responses[0][1]),
            "source_b": str(responses[1][1]),
            "totals_delta_b_minus_a": None,
            "top_diff_wells_steps": [],
            "matched_rows": 0,
            "unmatched_rows": None,
        }
    keyed: list[dict[tuple[str, int], dict[str, float]]] = []
    for payload, _ in responses:
        intervals = payload.get("interval_response") if isinstance(payload, Mapping) else None
        if not isinstance(intervals, list):
            return {
                "recorded": False,
                "reason": "an observation response has no interval_response rows",
                "source_a": str(responses[0][1]),
                "source_b": str(responses[1][1]),
                "totals_delta_b_minus_a": None,
                "top_diff_wells_steps": [],
                "matched_rows": 0,
                "unmatched_rows": None,
            }
        rows: dict[tuple[str, int], dict[str, float]] = {}
        for position, row in enumerate(intervals):
            if context is not None and position % 256 == 0:
                context.check_cancelled()
            if not isinstance(row, Mapping) or not isinstance(row.get("well"), str):
                continue
            step = row.get("control_step")
            if not isinstance(step, int) or isinstance(step, bool):
                continue
            metrics = {
                key: float(row[key])
                for key in ("oil_mass_delta", "injection_volume_delta")
                if isinstance(row.get(key), (int, float)) and not isinstance(row.get(key), bool)
            }
            if len(metrics) == 2:
                rows[(row["well"], step)] = metrics
        keyed.append(rows)
    shared = sorted(set(keyed[0]) & set(keyed[1]), key=lambda pair: (pair[1], pair[0]))
    if not shared:
        return {
            "recorded": False,
            "reason": "the OPM responses share no well/control_step rows",
            "source_a": str(responses[0][1]),
            "source_b": str(responses[1][1]),
            "totals_delta_b_minus_a": None,
            "top_diff_wells_steps": [],
            "matched_rows": 0,
            "unmatched_rows": len(keyed[0]) + len(keyed[1]),
        }
    totals_a = {key: sum(keyed[0][identity][key] for identity in shared) for key in ("oil_mass_delta", "injection_volume_delta")}
    totals_b = {key: sum(keyed[1][identity][key] for identity in shared) for key in ("oil_mass_delta", "injection_volume_delta")}
    deltas = {
        key: sum(keyed[1][identity][key] - keyed[0][identity][key] for identity in shared)
        for key in ("oil_mass_delta", "injection_volume_delta")
    }
    differences = [
        {
            "well": well,
            "control_step": step,
            "oil_mass_delta_b_minus_a": keyed[1][(well, step)]["oil_mass_delta"] - keyed[0][(well, step)]["oil_mass_delta"],
            "injection_volume_delta_b_minus_a": keyed[1][(well, step)]["injection_volume_delta"] - keyed[0][(well, step)]["injection_volume_delta"],
        }
        for well, step in shared
    ]
    oil_rank = {
        (row["well"], row["control_step"]): rank
        for rank, row in enumerate(sorted(differences, key=lambda item: abs(item["oil_mass_delta_b_minus_a"]), reverse=True))
    }
    injection_rank = {
        (row["well"], row["control_step"]): rank
        for rank, row in enumerate(sorted(differences, key=lambda item: abs(item["injection_volume_delta_b_minus_a"]), reverse=True))
    }
    differences.sort(
        key=lambda row: min(
            oil_rank[(row["well"], row["control_step"])],
            injection_rank[(row["well"], row["control_step"])],
        )
    )
    return {
        "recorded": True,
        "reason": None,
        "source_a": str(responses[0][1]),
        "source_b": str(responses[1][1]),
        "totals_a": totals_a,
        "totals_b": totals_b,
        "totals_delta_b_minus_a": deltas,
        "top_diff_wells_steps": differences[:50],
        "matched_rows": len(shared),
        "unmatched_rows": len(keyed[0]) + len(keyed[1]) - 2 * len(shared),
    }


def _comparison_conclusion_markdown(
    left: Located,
    right: Located,
    comparability: Mapping[str, Any],
    economic: Mapping[str, Any],
    production: Mapping[str, Any],
    delta_npv: float | None,
    lang: str,
) -> str:
    status_a = left.manifest.get("status", "not recorded")
    status_b = right.manifest.get("status", "not recorded")
    npv_a = left.manifest.get("verified_npv")
    npv_b = right.manifest.get("verified_npv")
    basis_a = "verified" if npv_a is not None else "predicted" if left.manifest.get("predicted_npv") is not None else None
    basis_b = "verified" if npv_b is not None else "predicted" if right.manifest.get("predicted_npv") is not None else None
    if npv_a is None:
        npv_a = left.manifest.get("predicted_npv")
    if npv_b is None:
        npv_b = right.manifest.get("predicted_npv")
    if lang == "ru":
        basis_label_a = {"verified": "OPM-проверенный", "predicted": "прогноз суррогата"}.get(basis_a, "источник не указан")
        basis_label_b = {"verified": "OPM-проверенный", "predicted": "прогноз суррогата"}.get(basis_b, "источник не указан")
    else:
        basis_label_a = {"verified": "OPM-verified", "predicted": "surrogate forecast"}.get(basis_a, "source unknown")
        basis_label_b = {"verified": "OPM-verified", "predicted": "surrogate forecast"}.get(basis_b, "source unknown")
    economic_lines = [
        f"- {key}: {value}"
        for key, value in (economic.get("deltas_b_minus_a") or {}).items()
        if isinstance(value, (int, float))
    ]
    production_delta = production.get("totals_delta_b_minus_a")
    production_lines = (
        [f"- {key}: {value}" for key, value in production_delta.items()]
        if isinstance(production_delta, Mapping)
        else []
    )
    sources = [
        f"- [A manifest](/api/jarvis/run-artifacts/{quote(left.run_id, safe='')}/manifest)",
        f"- [B manifest](/api/jarvis/run-artifacts/{quote(right.run_id, safe='')}/manifest)",
    ]
    if economic.get("recorded") is True:
        sources.extend([
            f"- [A annual economics](/api/jarvis/run-artifacts/{quote(left.run_id, safe='')}/npv-table)",
            f"- [B annual economics](/api/jarvis/run-artifacts/{quote(right.run_id, safe='')}/npv-table)",
        ])
    if production.get("recorded") is True:
        sources.extend([
            f"- [A OPM response](/api/jarvis/run-artifacts/{quote(left.run_id, safe='')}/opm-response)",
            f"- [B OPM response](/api/jarvis/run-artifacts/{quote(right.run_id, safe='')}/opm-response)",
        ])
    if lang == "ru":
        return "\n".join([
            f"# Сравнительное инженерное заключение: {left.run_id} и {right.run_id}", "",
            "## Сопоставимость", f"- Статус: `{comparability.get('status', 'unverified')}`.",
            f"- {comparability.get('note', 'Сопоставимость не установлена.')}", "",
            "## Зарегистрированные результаты", f"- A: `{status_a}`, ЧДД ({basis_label_a})={npv_a if npv_a is not None else 'не записан'}.",
            f"- B: `{status_b}`, ЧДД ({basis_label_b})={npv_b if npv_b is not None else 'не записан'}.",
            f"- Арифметическая разница ЧДД (B − A): {delta_npv if delta_npv is not None else 'не вычислена: источники ЧДД различаются или значение не записано'}.", "",
            "## Экономические строки (B − A)", *(economic_lines or ["- Данные обеих таблиц годовой экономики не записаны."]), "",
            "## OPM отклик (B − A)",
            f"- Совпадающих строк скважина/шаг: {production.get('matched_rows', 0)}; без пары: {production.get('unmatched_rows') if production.get('unmatched_rows') is not None else 'неизвестно'}.",
            *(production_lines or [f"- Сравнение недоступно: {production.get('reason') or 'нет записанных OPM response данных'}."]), "",
            "Разницы являются арифметическим сравнением записанных результатов. Они не устанавливают причинный вклад отдельного изменения и не рекомендуют план, особенно при rejected или incomparable результатах.", "",
            "## Источники", *sources, "",
        ])
    return "\n".join([
        f"# Comparative engineering conclusion: {left.run_id} and {right.run_id}", "",
        "## Comparability", f"- Status: `{comparability.get('status', 'unverified')}`.",
        f"- {comparability.get('note', 'Comparability is not established.')}", "",
        "## Recorded results", f"- A: `{status_a}`, NPV ({basis_label_a})={npv_a if npv_a is not None else 'not recorded'}.",
        f"- B: `{status_b}`, NPV ({basis_label_b})={npv_b if npv_b is not None else 'not recorded'}.",
        f"- Arithmetic NPV delta (B − A): {delta_npv if delta_npv is not None else 'not calculated: NPV sources differ or a value is not recorded'}.", "",
        "## Economic line items (B − A)", *(economic_lines or ["Annual economics tables for both runs are not recorded."]), "",
        "## OPM response (B − A)",
        f"- Matched well/step rows: {production.get('matched_rows', 0)}; unmatched: {production.get('unmatched_rows') if production.get('unmatched_rows') is not None else 'unknown'}.",
        *(production_lines or [f"- Comparison unavailable: {production.get('reason') or 'recorded OPM response data is missing'}."]), "",
        "These are arithmetic differences between recorded results. They do not establish a causal contribution of an individual change or recommend a plan, especially for rejected or incomparable runs.", "",
        "## Sources", *sources, "",
    ])


def compare_runs(context: ToolContext, arguments: Mapping[str, Any]) -> Card:
    items = _located(context)
    if len(items) < 2 and (arguments.get("a") is None or arguments.get("b") is None):
        raise ToolFailure(
            f"{NO_RUNS}: a comparison needs two runs, but {len(items)} was "
            "found; there is nothing to compare"
        )
    left_id = arguments.get("a")
    right_id = arguments.get("b")
    left = _find(context, str(left_id) if left_id is not None else items[1].run_id)
    right = _find(context, str(right_id) if right_id is not None else items[0].run_id)
    if left.run_id == right.run_id:
        raise ToolFailure(
            f"run {left.run_id} is being compared with itself: the difference "
            "is always zero, name two different runs"
        )
    a = _side(left, context)
    b = _side(right, context)
    comparison = _read_json(right.directory / COMPARISON_FILE)
    delta = None
    delta_reason = None
    if (
        isinstance(a["npv"], (int, float))
        and isinstance(b["npv"], (int, float))
        and a["npv_basis"] == b["npv_basis"]
    ):
        delta = float(b["npv"]) - float(a["npv"])
    else:
        delta_reason = "NPV sources differ or a value is not recorded; no mixed-basis delta was calculated"
    comparability = _comparability(left, right, context.lang)
    economics = _economic_breakdown(left, right)
    production = _production_injection_breakdown(left, right, context)
    payload = {
        "a": a,
        "b": b,
        "delta_npv": delta,
        "delta_npv_reason": delta_reason,
        "comparability": comparability,
        "economic_breakdown": economics,
        "production_injection": production,
        "conclusion_markdown": _comparison_conclusion_markdown(
            left, right, comparability, economics, production, delta, context.lang
        ),
        "top_diff_wells": (comparison or {}).get("top_diff_wells") or [],
        "comparison": dict(comparison) if comparison is not None else None,
        "comparison_reason": (
            None
            if comparison is not None
            else (
                f"{NO_COMPARISON}: run {right.run_id} has no "
                f"{COMPARISON_FILE} file, so the breakdown of the difference "
                "by well is unknown"
            )
        ),
    }
    return Card(
        type="compare",
        title=_title("compare", context.lang, a=left.run_id, b=right.run_id),
        payload=payload,
        provenance=PROVENANCE,
    )


def latest_run(context: ToolContext) -> RunRecord | None:
    try:
        return context.run_store().read()
    except (ToolFailure, RunError):
        return None
