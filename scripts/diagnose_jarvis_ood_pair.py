"""Compare unchanged and edited constraints through the same web search worker."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import statistics
import time

from backend.shared.env_file import load_env_file


ROOT = Path(__file__).resolve().parents[1]
SOURCE_RUN = ROOT / "out/web-runs/web-20260927-181807-7bd864e6"


def digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def summary(path: Path) -> dict[str, object]:
    data = json.loads((path / "diagnostics.json").read_text())
    evaluations = data.get("evaluations") or []
    scores = [float(row["ood_score"]) for row in evaluations if isinstance(row.get("ood_score"), (int, float))]
    return {
        "status": json.loads((path / "job.json").read_text()).get("status"),
        "evaluations": len(evaluations),
        "feasible": sum(row.get("feasible") is True for row in evaluations),
        "seed": data.get("seed"),
        "threshold": next((row.get("scenario_ood") for row in evaluations if row.get("scenario_ood") is not None), None),
        "score_min": min(scores) if scores else None,
        "score_median": statistics.median(scores) if scores else None,
        "score_max": max(scores) if scores else None,
        "strategies": {name: sum(row.get("strategy") == name for row in evaluations)
                       for name in sorted({str(row.get("strategy")) for row in evaluations})},
        "first_ten": [
            {"theta": row.get("theta"), "ood_score": row.get("ood_score"),
             "schedule_hash": row.get("schedule_hash"), "feasible": row.get("feasible"),
             "reason": (row.get("violations") or [{}])[0].get("what")}
            for row in evaluations[:10]
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-run", type=Path, default=SOURCE_RUN)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    source = args.source_run.resolve()
    output = args.output.resolve()
    if output.exists():
        parser.error("output already exists; use a fresh diagnostic directory")
    load_env_file(ROOT / ".env.local")
    os.chdir(ROOT)
    from backend.contexts.runs.application.web_runs import WebRuns

    saved_job = json.loads((source / "job.json").read_text())
    baseline = saved_job["case_request"]["base_constraints"]
    edited = json.loads((source / "constraints.json").read_text())
    if baseline == edited:
        parser.error("the source run has no case change")
    output.mkdir(parents=True)
    (output / "pair-input.json").write_text(json.dumps({
        "source_run": source.name,
        "source_job_sha256": hashlib.sha256((source / "job.json").read_bytes()).hexdigest(),
        "baseline_sha256": digest(baseline),
        "edited_sha256": digest(edited),
        "budget": 10,
        "worker": "backend.interfaces.cli.web_run_worker",
        "cases": {"baseline": baseline, "edited": edited},
    }, ensure_ascii=False, indent=2) + "\n")
    runs = WebRuns(output)
    records: dict[str, dict[str, object]] = {}
    for label, constraints in (("baseline", baseline), ("edited", edited)):
        started = runs.start({"mode": "search", "budget": 10, "constraints": constraints})
        run_id = str(started["run_id"])
        directory = output / run_id
        print(f"{label}: {run_id} started", flush=True)
        previous_stage = None
        try:
            while True:
                current = json.loads((directory / "job.json").read_text())
                if current.get("status") != "running":
                    break
                progress = directory / "search-progress.json"
                if progress.is_file():
                    value = json.loads(progress.read_text())
                    stage = (value.get("stage"), value.get("step"))
                    if stage != previous_stage:
                        print(f"{label}: {stage[0]} {stage[1]}/{value.get('total')}", flush=True)
                        previous_stage = stage
                time.sleep(1)
        except BaseException:
            if runs.store.read(directory).get("status") == "running":
                runs.cancel(run_id)
            raise
        records[label] = {"run_id": run_id, **summary(directory)}
        print(f"{label}: {records[label]['status']}, {records[label]['feasible']}/{records[label]['evaluations']} feasible", flush=True)
    left = records["baseline"]["first_ten"]
    right = records["edited"]["first_ten"]
    paired = [
        {"index": index, "same_theta": a["theta"] == b["theta"],
         "baseline_ood": a["ood_score"], "edited_ood": b["ood_score"],
         "delta": (b["ood_score"] - a["ood_score"])
         if isinstance(a["ood_score"], (int, float)) and isinstance(b["ood_score"], (int, float)) else None,
         "same_schedule_hash": (a["schedule_hash"] == b["schedule_hash"])
         if a["schedule_hash"] and b["schedule_hash"] else None}
        for index, (a, b) in enumerate(zip(left, right), 1)
    ]
    document = {"baseline": records["baseline"], "edited": records["edited"], "paired_first_ten": paired}
    (output / "pair-result.json").write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n")
    print("paired result: " + str(output / "pair-result.json"), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
