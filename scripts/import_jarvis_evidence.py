from __future__ import annotations

import argparse
from pathlib import Path

from backend.contexts.assistant.infrastructure.artifacts import RunError, RunStore, import_decision_evidence


def main() -> int:
    parser = argparse.ArgumentParser(description="Index recorded Jarvis decision evidence by well and control step.")
    parser.add_argument("runs", type=Path, help="directory containing run subdirectories")
    parser.add_argument("run_id", nargs="?", help="index one run; default indexes every run with recorded explanations")
    args = parser.parse_args()
    store = RunStore(args.runs)
    selected = (args.run_id,) if args.run_id else store.run_ids()
    indexed = 0
    for run_id in selected:
        record = store.read(run_id)
        if not (record.directory / "well-explanations.json").is_file():
            print(f"{run_id}: no recorded decision journal; result-only run")
            continue
        try:
            count = import_decision_evidence(record.directory)
        except RunError as error:
            parser.error(str(error))
        indexed += count
        print(f"{run_id}: indexed {count} well-step decisions")
    print(f"total indexed decisions: {indexed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
