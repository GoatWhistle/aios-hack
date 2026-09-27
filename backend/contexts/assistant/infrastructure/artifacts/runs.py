from __future__ import annotations

import json
import hashlib
import math
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Mapping

from backend.contexts.assistant.domain.errors import RunError
from backend.shared.hashing import canonical_hash, canonical_schedule_hash
from backend.shared.settings import Settings

RUNS_ENV_VAR = "AIOS_JARVIS_RUNS"
OUT_ENV_VAR = "AIOS_OUT_DIR"
MANIFEST_FILE = "manifest.json"
SUBMISSION_DIR = "submission"
CLAIMED_NPV_FILE = "claimed_npv.json"
SCHEDULE_INCLUDE_FILE = "well_schedule.inc"
VALIDATION_DIR = "validation"
VALIDATION_RESULT_FILE = "result.json"
CONSTRAINTS_REPORT_FILE = "constraints_report.json"
NOT_RECORDED = "not-recorded"
EVIDENCE_FILE = "decision-evidence.jsonl"
EVIDENCE_INDEX_FILE = "decision-evidence-index.json"
ALTERNATIVE_STATUSES = frozenset(
    {"recorded-comparison", "state-comparison-only", "separate-calculation-required"}
)


MANIFEST_PROVENANCE_FIELDS: tuple[str, ...] = (
    "model_version",
    "npv_head_version",
    "scenario_ood_version",
    "feature_context_sha256",
    "constraints_hash",
    "deck_hash",
    "normatives_sha256",
    "opm_image",
    "git_commit",
    "seed",
    "search_strategy",
    "policy_equilibrium",
    "iterations",
    "self_consistent",
)


CLAIMED_NPV_FIELDS: tuple[str, ...] = (
    "canonical_schedule_hash",
    "content_hash_submission",
    "claimed_npv_rub",
    "source_run_id",
    "response_hash",
    "deck_hash",
    "economics_config_hash",
    "methodology_version_hash",
    "constraints_hash",
    "opm_image",
    "git_commit",
    "created_at",
)


def default_runs_root(settings: Settings | None = None) -> Path:
    resolved = Settings.from_env() if settings is None else settings
    if resolved.jarvis_runs is not None:
        return resolved.jarvis_runs
    if resolved.raw.get(OUT_ENV_VAR):
        return resolved.out_root / "runs"
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "pyproject.toml").is_file():
            return parent / "out" / "runs"
    raise RunError(
        "the runs directory was not found: point at it with the environment "
        f"variable {RUNS_ENV_VAR} or run from the repository root that holds out/runs"
    )


@dataclass(frozen=True, slots=True)
class RunRecord:
    run_id: str
    directory: Path
    manifest: Mapping[str, Any]
    validation: Mapping[str, Any] | None
    constraints_report: Mapping[str, Any] | None
    submission: Mapping[str, Any] | None
    schedule_include: bool
    origin: Mapping[str, Any] | None = None
    opm_result: Mapping[str, Any] | None = None
    prediction: Mapping[str, Any] | None = None
    economics: Mapping[str, Any] | None = None

    def verified_constraints(self) -> Mapping[str, Any] | None:
        """Return run constraints only when their canonical digest matches the manifest."""
        path = self.directory / "inputs" / "constraints.json"
        constraints = _read_optional_json(path)
        if constraints is None:
            return None
        expected = self.manifest.get("constraints_hash")
        if not isinstance(expected, str) or canonical_hash(constraints) != expected:
            raise RunError(f"constraints provenance does not match run {self.run_id}")
        return constraints

    def decision_evidence(self, well: str, step: int) -> Mapping[str, Any] | None:
        """Read one indexed, recorded explanation without loading the journal."""
        index_path = self.directory / EVIDENCE_INDEX_FILE
        data_path = self.directory / EVIDENCE_FILE
        if not index_path.is_file() or not data_path.is_file():
            return None
        index = _read_optional_json(index_path)
        if index is None or index.get("schema_version") != 1:
            raise RunError(f"decision evidence index has an unsupported schema: {index_path}")
        if index.get("run_id") != self.run_id or index.get("schedule_hash") != self.manifest.get("schedule_hash"):
            raise RunError(f"decision evidence index provenance does not match run {self.run_id}")
        control_steps = index.get("control_steps")
        if isinstance(control_steps, int) and (step < 0 or step >= control_steps):
            terminal = " The final control date is terminal and is not a decision step." if step == control_steps else ""
            raise RunError(
                f"control step {step} is outside run {self.run_id}: valid decision steps are "
                f"0 through {control_steps - 1}.{terminal}"
            )
        offsets = index.get("offsets")
        if not isinstance(offsets, dict):
            raise RunError(f"decision evidence index has no valid offsets map: {index_path}")
        key = f"{well}:{step}"
        offset = offsets.get(key)
        if not isinstance(offset, int) or offset < 0:
            return None
        try:
            with data_path.open("rb") as stream:
                stream.seek(offset)
                raw = stream.readline()
            loaded = json.loads(raw)
        except (OSError, json.JSONDecodeError) as error:
            raise RunError(f"cannot read indexed decision evidence {key} from {data_path}: {error}") from error
        if not isinstance(loaded, dict) or str(loaded.get("well")) != well or loaded.get("step") != step:
            raise RunError(f"decision evidence index points to the wrong record for {key}")
        return loaded

    def decision_series(self, well: str) -> Mapping[str, Any] | None:
        """Build one run-backed time series from indexed observations and final commands."""
        index_path = self.directory / EVIDENCE_INDEX_FILE
        data_path = self.directory / EVIDENCE_FILE
        if not index_path.is_file() or not data_path.is_file():
            return None
        index = _read_optional_json(index_path)
        if index is None or index.get("schema_version") != 1:
            raise RunError(f"decision evidence index has an unsupported schema: {index_path}")
        if index.get("run_id") != self.run_id or index.get("schedule_hash") != self.manifest.get("schedule_hash"):
            raise RunError(f"decision evidence index provenance does not match run {self.run_id}")
        dates = index.get("dates")
        offsets = index.get("offsets")
        control_steps = index.get("control_steps")
        if not isinstance(dates, list) or not isinstance(offsets, dict) or not isinstance(control_steps, int):
            raise RunError(f"decision evidence index has an invalid date axis or offsets map: {index_path}")
        if len(dates) != control_steps:
            raise RunError(f"decision evidence index date axis does not match its control step count: {index_path}")
        rows: list[dict[str, Any]] = []
        role: str | None = None
        scheduled_rate: float | None = None
        try:
            with data_path.open("rb") as stream:
                for step, step_date in enumerate(dates):
                    offset = offsets.get(f"{well}:{step}")
                    if not isinstance(offset, int) or offset < 0:
                        continue
                    stream.seek(offset)
                    record = json.loads(stream.readline())
                    if not isinstance(record, dict) or str(record.get("well")) != well or record.get("step") != step:
                        raise RunError(f"decision evidence index points to the wrong record for {well}:{step}")
                    observation = record.get("input_observation")
                    if not isinstance(observation, Mapping):
                        continue
                    observed_role = observation.get("role")
                    if not isinstance(observed_role, str):
                        continue
                    if role is not None and observed_role != role:
                        raise RunError(f"well {well} changes role in run {self.run_id}; a single rate series is ambiguous")
                    role = observed_role
                    if scheduled_rate is None:
                        baseline = observation.get("setpoint_m3_per_day")
                        if isinstance(baseline, (int, float)) and not isinstance(baseline, bool) and math.isfinite(float(baseline)):
                            scheduled_rate = float(baseline)
                    observed_key = "injection_rate_m3_per_day" if observed_role == "INJ" else "liquid_rate_m3_per_day"
                    observed_value = observation.get(observed_key)
                    input_rate = (
                        float(observed_value)
                        if isinstance(observed_value, (int, float)) and not isinstance(observed_value, bool) and math.isfinite(float(observed_value))
                        else None
                    )
                    final_events = record.get("final_schedule_events")
                    if isinstance(final_events, list):
                        expected_kind = "SET_RATE" if observed_role == "INJ" else "SET_LRAT"
                        for event in final_events:
                            if not isinstance(event, Mapping) or str(event.get("well")) != well or event.get("kind") != expected_kind:
                                continue
                            value = event.get("value")
                            if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value)):
                                scheduled_rate = float(value)
                    rows.append({"step": step, "date": step_date, "input_rate": input_rate, "scheduled_rate": scheduled_rate})
        except (OSError, json.JSONDecodeError) as error:
            raise RunError(f"cannot read indexed decision series for well {well} from {data_path}: {error}") from error
        if not rows or role is None:
            return None
        return {
            "run_id": self.run_id,
            "well": well,
            "role": role,
            "metric": "injection_rate" if role == "INJ" else "liquid_rate",
            "unit": "m3/day",
            "input_source": "input_observation",
            "schedule_source": "final_schedule_events",
            "rows": rows,
        }

    def response_state_at_date(self, well: str, target_date: str) -> Mapping[str, Any] | None:
        """Read one OPM state only when it matches the run's recorded economics response."""
        schedule_hash = self.manifest.get("schedule_hash")
        expected_hash = (self.economics or {}).get("source_response_hash")
        if (
            not isinstance(schedule_hash, str)
            or not re.fullmatch(r"[0-9a-f]{64}", schedule_hash)
            or not isinstance(expected_hash, str)
            or not re.fullmatch(r"[0-9a-f]{64}", expected_hash)
        ):
            return None
        response = _read_optional_json(
            self.directory / "observation" / schedule_hash / "response.json"
        )
        if response is None or response.get("response_hash") != expected_hash:
            return None
        deck_dates = _read_deck_dates(self.directory)
        try:
            deck_date_index = deck_dates.index(target_date)
        except ValueError:
            return None
        state_rows = response.get("state_at_date")
        if not isinstance(state_rows, list):
            return None
        matches = [
            row
            for row in state_rows
            if isinstance(row, Mapping)
            and str(row.get("well")) == str(well)
            and row.get("deck_date_index") == deck_date_index
        ]
        if len(matches) > 1:
            raise RunError(
                f"duplicate OPM response state for well {well} on {target_date} in run {self.run_id}"
            )
        return matches[0] if matches else None

    def step_for_date(self, requested: str) -> int:
        index = _read_optional_json(self.directory / EVIDENCE_INDEX_FILE)
        if index is None or index.get("schema_version") != 1:
            raise RunError(f"decision evidence index is unavailable for run {self.run_id}")
        if index.get("run_id") != self.run_id or index.get("schedule_hash") != self.manifest.get("schedule_hash"):
            raise RunError(f"decision evidence index provenance does not match run {self.run_id}")
        dates = index.get("dates", []) if index is not None else []
        if not isinstance(dates, list):
            raise RunError(f"decision evidence date axis is invalid for run {self.run_id}")
        for step, value in enumerate(dates):
            if isinstance(value, str) and (value == requested or value.startswith(requested)):
                return step
        raise RunError(
            f"date {requested!r} is outside the recorded control-date axis of run {self.run_id}"
        )

    def field(self, name: str) -> Any:
        if name not in self.manifest:
            return None
        return self.manifest[name]

    def recorded(self, name: str) -> bool:
        return self.manifest.get(name) is not None

    def documents(self) -> tuple[Mapping[str, Any], ...]:
        collected: list[Mapping[str, Any]] = [self.manifest]
        for part in (self.validation, self.constraints_report, self.submission):
            if part is not None:
                collected.append(part)
        return tuple(collected)


def _read_optional_json(path: Path) -> Mapping[str, Any] | None:
    if not path.is_file():
        return None
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise RunError(
            f"artifact {path} does not parse as JSON: {error}"
        ) from error
    if not isinstance(loaded, dict):
        raise RunError(f"artifact {path} is not a JSON object")
    return loaded


class RunStore:
    def __init__(self, root: Path | str | None = None) -> None:
        self._root = Path(root) if root is not None else default_runs_root()

    @property
    def root(self) -> Path:
        return self._root

    def exists(self) -> bool:
        return self._root.is_dir()

    def registered_scenario(self, run_id: str) -> Mapping[str, Any] | None:
        """Return repository-level scenario metadata without inventing a run manifest."""
        settings = Settings.from_env()
        path = settings.project_root / "artifacts" / "jarvis-scenario-registry.json"
        registry = _read_optional_json(path)
        if registry is None or registry.get("schema_version") != 1:
            return None
        entries = registry.get("entries")
        if not isinstance(entries, list):
            return None
        for entry in entries:
            if isinstance(entry, dict) and entry.get("run_id") == run_id:
                return entry
        return None

    def run_ids(self) -> tuple[str, ...]:
        if not self._root.is_dir():
            return ()
        found = [
            entry.name
            for entry in self._root.iterdir()
            if entry.is_dir() and (entry / MANIFEST_FILE).is_file()
        ]
        return tuple(sorted(found))

    def latest_run_id(self) -> str | None:
        if not self._root.is_dir():
            return None
        stamped: list[tuple[float, str]] = []
        for name in self.run_ids():
            path = self._root / name / MANIFEST_FILE
            stamped.append((path.stat().st_mtime, name))
        if not stamped:
            return None
        stamped.sort()
        return stamped[-1][1]

    def read(self, run_id: str | None = None) -> RunRecord:
        name = run_id if run_id is not None else self.latest_run_id()
        if name is None:
            raise RunError(
                "the runs directory holds no run with a manifest: "
                f"{self._root}; no calculation has been made yet"
            )
        if Path(name).name != name:
            raise RunError(
                f"run identifier {name!r} is not a directory name"
            )
        directory = self._root / name
        manifest_path = directory / MANIFEST_FILE
        if not manifest_path.is_file():
            known = self.run_ids()
            listed = ", ".join(known) if known else "none"
            raise RunError(
                f"run {name!r} was not found in {self._root}: the manifest "
                f"{manifest_path} is absent; known runs are {listed}"
            )
        manifest = _read_optional_json(manifest_path)
        if manifest is None:
            raise RunError(f"the manifest of run {name!r} cannot be read: {manifest_path}")
        submission_dir = directory / SUBMISSION_DIR
        return RunRecord(
            run_id=name,
            directory=directory,
            manifest=manifest,
            validation=_read_optional_json(
                directory / VALIDATION_DIR / VALIDATION_RESULT_FILE
            ),
            constraints_report=_read_optional_json(
                directory / VALIDATION_DIR / CONSTRAINTS_REPORT_FILE
            ),
            submission=_read_optional_json(submission_dir / CLAIMED_NPV_FILE),
            schedule_include=(submission_dir / SCHEDULE_INCLUDE_FILE).is_file(),
            origin=_read_optional_json(directory / "inputs" / "origin.json"),
            opm_result=_read_optional_json(directory / "opm-result.json"),
            prediction=_read_optional_json(directory / "prediction" / "result.json"),
            economics=_read_optional_json(directory / "economics" / "result.json"),
        )


def import_decision_evidence(run_directory: Path | str) -> int:
    """Build a deterministic offset index from a run's packed explanations."""
    directory = Path(run_directory)
    source = directory / "well-explanations.json"
    if not source.is_file():
        raise RunError(f"recorded decision journal is missing: {source}")
    try:
        packed = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RunError(f"cannot read recorded decision journal {source}: {error}") from error
    if not isinstance(packed, dict) or not isinstance(packed.get("explanations"), list):
        raise RunError(f"recorded decision journal has an invalid structure: {source}")
    manifest = _read_optional_json(directory / MANIFEST_FILE)
    if manifest is None or manifest.get("run_id") != directory.name:
        raise RunError(f"run identity does not match its manifest: {directory}")
    schedule_hash = manifest.get("schedule_hash")
    if packed.get("run_id") != directory.name or packed.get("schedule_hash") != schedule_hash:
        raise RunError(f"recorded decision journal provenance does not match run {directory.name}")
    required_lists = (
        "rule_facts",
        "hierarchy_proposed_events",
        "final_schedule_events",
        "group_allocations",
    )
    for line_number, row in enumerate(packed["explanations"], start=1):
        if not isinstance(row, Mapping):
            raise RunError(f"invalid decision evidence record {line_number} in {source}")
        if (
            not isinstance(row.get("well"), (str, int))
            or isinstance(row.get("well"), bool)
            or not isinstance(row.get("step"), int)
            or isinstance(row.get("step"), bool)
            or row["step"] < 0
            or not isinstance(row.get("input_observation"), Mapping)
            or any(not isinstance(row.get(key), list) for key in required_lists)
            or not isinstance(row.get("journal_line"), int)
            or isinstance(row.get("journal_line"), bool)
            or not isinstance(row.get("note"), str)
        ):
            raise RunError(f"invalid decision evidence schema at record {line_number} in {source}")
        if any(
            not isinstance(item, Mapping)
            for key in required_lists
            for item in row[key]
        ):
            raise RunError(f"invalid nested decision evidence schema at record {line_number} in {source}")
        alternative_status = row.get("alternative_status")
        if alternative_status is not None and alternative_status not in ALTERNATIVE_STATUSES:
            raise RunError(f"invalid alternative comparison status at record {line_number} in {source}")
        if alternative_status in {"recorded-comparison", "state-comparison-only"}:
            comparison = row.get("alternative_comparison")
            evidence_flag = "recorded" if alternative_status == "recorded-comparison" else "measured"
            if not isinstance(comparison, Mapping) or comparison.get(evidence_flag) is not True:
                raise RunError(
                    f"alternative comparison status has no supporting evidence at record {line_number} in {source}"
                )
    schedule = _read_optional_json(directory / "schedule" / "schedule.json")
    if schedule is not None:
        try:
            actual_schedule_hash = canonical_schedule_hash(
                schedule["initial_state"],
                schedule["fixed_deck_events"],
                schedule["control_events"],
            )
        except (KeyError, TypeError) as error:
            raise RunError(f"schedule artifact has an invalid structure: {directory / 'schedule' / 'schedule.json'}") from error
        if actual_schedule_hash != schedule_hash:
            raise RunError(f"schedule hash mismatch for run {directory.name}")
    journal = directory / "inputs" / "decision-journal.jsonl"
    expected_journal_hash = packed.get("journal_sha256")
    if journal.is_file() and expected_journal_hash:
        digest = hashlib.sha256(journal.read_bytes()).hexdigest()
        if digest != expected_journal_hash:
            raise RunError(f"decision journal hash mismatch for run {directory.name}")
    if journal.is_file():
        observations: set[str] = set()
        try:
            with journal.open(encoding="utf-8") as stream:
                for line_number, line in enumerate(stream, start=1):
                    item = json.loads(line)
                    state = item.get("state") if isinstance(item, dict) else None
                    wells = state.get("wells") if isinstance(state, dict) else None
                    step = state.get("control_step") if isinstance(state, dict) else None
                    if not isinstance(wells, dict) or not isinstance(step, int):
                        raise RunError(f"invalid observation row {line_number} in {journal}")
                    observations.update(f"{well}:{step}" for well in wells)
        except (OSError, json.JSONDecodeError) as error:
            raise RunError(f"cannot index recorded observations from {journal}: {error}") from error
        expected = {f"{row['well']}:{row['step']}" for row in packed["explanations"]}
        if observations != expected:
            raise RunError(
                f"recorded observations and decision explanations do not match for run {directory.name}: "
                f"{len(observations - expected)} observations lack an evidence row, "
                f"{len(expected - observations)} evidence rows lack an observation"
            )
    # The economics result must point at the response produced by this exact
    # schedule. A response file is optional for older/imported runs, but when
    # economics names one we must be able to verify it before indexing facts.
    economics = _read_optional_json(directory / "economics" / "result.json")
    expected_response_hash = (
        economics.get("source_response_hash") if isinstance(economics, Mapping) else None
    )
    response_status = "not-recorded"
    response: Mapping[str, Any] | None = None
    if expected_response_hash is not None:
        if not isinstance(expected_response_hash, str) or not re.fullmatch(
            r"[0-9a-f]{64}", expected_response_hash
        ):
            raise RunError(f"economics source response hash is invalid for run {directory.name}")
        response_path = directory / "observation" / str(schedule_hash) / "response.json"
        response = _read_optional_json(response_path)
        if response is None:
            raise RunError(
                f"economics source response is missing for run {directory.name}: {response_path}"
            )
        actual_response_hash = response.get("response_hash")
        if actual_response_hash != expected_response_hash:
            raise RunError(
                f"economics source response hash does not match observation response for run {directory.name}"
            )
        response_status = "verified"
    offsets: dict[str, int] = {}
    origin = _read_optional_json(directory / "inputs" / "origin.json") or {}
    control_dates = _read_control_dates(directory)
    schedule_meta = schedule.get("meta", {}) if schedule is not None else {}
    control_steps = schedule_meta.get("n_intervals") if isinstance(schedule_meta, Mapping) else None
    date_axis_status = "unverified"
    interval_steps: set[int] = set()
    if response_status == "verified":
        interval_rows = response.get("interval_response") if response is not None else None
        if not isinstance(interval_rows, list):
            raise RunError(f"verified response has no interval axis for run {directory.name}")
        expected_steps = set(range(int(control_steps or 0)))
        response_pairs: set[str] = set()
        for row in interval_rows:
            if not isinstance(row, Mapping) or not isinstance(row.get("control_step"), int):
                raise RunError(f"verified response has an invalid interval row for run {directory.name}")
            step = row["control_step"]
            if step not in expected_steps or not isinstance(row.get("well"), (str, int)):
                raise RunError(f"verified response interval is outside the schedule axis for run {directory.name}")
            interval_steps.add(step)
            response_pairs.add(f"{row['well']}:{step}")
        if interval_steps != expected_steps:
            raise RunError(f"verified response interval steps do not cover the schedule for run {directory.name}")
        missing_response_rows = {
            f"{row['well']}:{row['step']}" for row in packed["explanations"]
        } - response_pairs
        if missing_response_rows:
            raise RunError(
                f"verified response does not cover {len(missing_response_rows)} recorded decisions for run {directory.name}"
            )
        if len(control_dates) != len(expected_steps):
            raise RunError(f"verified response cannot be joined to a complete OPM date axis for run {directory.name}")
        date_axis_status = "verified"
    target = directory / EVIDENCE_FILE
    temporary = target.with_suffix(".jsonl.tmp")
    position = 0
    try:
        with temporary.open("wb") as stream:
            for row in packed["explanations"]:
                if not isinstance(row, dict) or not isinstance(row.get("well"), (str, int)) or not isinstance(row.get("step"), int):
                    raise RunError(f"invalid decision evidence record in {source}")
                key = f"{row['well']}:{row['step']}"
                if key in offsets:
                    raise RunError(f"duplicate decision evidence record {key} in {source}")
                step = row["step"]
                record = {
                    "schema_version": 1,
                    "run_id": directory.name,
                    "scenario": origin.get("kind", "unclassified"),
                    "date": control_dates[step] if step < len(control_dates) else None,
                    "date_source": "opm/deck/Model_Z_sch.inc" if step < len(control_dates) else None,
                    "date_axis_status": date_axis_status,
                    "date_response_hash": expected_response_hash if date_axis_status == "verified" else None,
                    "alternative_status": "separate-calculation-required",
                    **row,
                }
                encoded = (json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")
                offsets[key] = position
                stream.write(encoded)
                position += len(encoded)
        temporary.replace(target)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    index_path = directory / EVIDENCE_INDEX_FILE
    index_tmp = index_path.with_suffix(".json.tmp")
    index_tmp.write_text(json.dumps({"schema_version": 1, "run_id": directory.name, "schedule_hash": schedule_hash, "journal_sha256": expected_journal_hash, "response_hash": expected_response_hash, "response_status": response_status, "date_axis_status": date_axis_status, "date_axis_source": "opm/deck/Model_Z_sch.inc" if control_dates else None, "control_steps": control_steps, "dates": control_dates, "record_count": len(offsets), "offsets": offsets}, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    index_tmp.replace(index_path)
    return len(offsets)


_MONTHS = {
    name: number
    for number, name in enumerate(
        ("JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"),
        start=1,
    )
}
_DECK_DATE = re.compile(r"^\s*(\d{1,2})\s+([A-Z]{3})\s+(\d{4})\s*/\s*$", re.MULTILINE)


def _read_control_dates(directory: Path) -> list[str]:
    """Read the control axis from the exact OPM schedule deck used by the run."""
    schedule = _read_optional_json(directory / "schedule" / "schedule.json") or {}
    meta = schedule.get("meta", {})
    t0_text = meta.get("t0") if isinstance(meta, Mapping) else None
    intervals = meta.get("n_intervals") if isinstance(meta, Mapping) else None
    control_count = meta.get("n_control_dates") if isinstance(meta, Mapping) else None
    deck = directory / "opm" / "deck" / "Model_Z_sch.inc"
    if not isinstance(t0_text, str) or not isinstance(intervals, int) or not isinstance(control_count, int) or not deck.is_file():
        return []
    try:
        t0 = date.fromisoformat(t0_text)
    except ValueError as error:
        raise RunError(f"invalid start date for run {directory.name}: {error}") from error
    dates = _read_deck_dates(directory)
    selected = [value for value in dates if date.fromisoformat(value) >= t0]
    if len(selected) != control_count or len(selected) != intervals + 1 or not selected or selected[0] != t0.isoformat():
        raise RunError(
            f"control-date axis for run {directory.name} does not match schedule metadata: "
            f"found {len(selected)} dates, expected {control_count} control dates for {intervals} intervals"
        )
    return selected[:-1]


def _read_deck_dates(directory: Path) -> list[str]:
    deck = directory / "opm" / "deck" / "Model_Z_sch.inc"
    if not deck.is_file():
        return []
    try:
        source = deck.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        raise RunError(f"cannot read the control-date axis for run {directory.name}: {error}") from error
    dates: list[str] = []
    for day_text, month_text, year_text in _DECK_DATE.findall(source):
        month = _MONTHS.get(month_text)
        if month is None:
            continue
        try:
            value = date(int(year_text), month, int(day_text))
        except ValueError:
            continue
        dates.append(value.isoformat())
    return dates
