from __future__ import annotations

import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

WORKER_MODULE = "backend.interfaces.cli.web_run_worker"
WORKER_TIMEOUT_SECONDS = 7200
WORKER_THREAD_LIMIT = "2"
WORKER_CANCELLED = 125


def run_worker(
    directory: Path,
    mode: str,
    budget: int,
    timeout: int = WORKER_TIMEOUT_SECONDS,
    cancel_event: threading.Event | None = None,
) -> int:
    environment = dict(
        os.environ,
        OMP_NUM_THREADS=WORKER_THREAD_LIMIT,
        MKL_NUM_THREADS=WORKER_THREAD_LIMIT,
    )
    command = [
        sys.executable,
        "-m",
        WORKER_MODULE,
        mode,
        "--directory",
        str(directory),
        "--budget",
        str(budget),
    ]
    with (directory / f"{mode}.log").open("w", encoding="utf-8") as log:
        process = subprocess.Popen(
            command,
            stdout=log,
            stderr=subprocess.STDOUT,
            env=environment,
            start_new_session=(os.name == "posix"),
        )
        deadline = time.monotonic() + timeout
        while process.poll() is None:
            if cancel_event is not None and cancel_event.is_set():
                if os.name == "posix":
                    os.killpg(process.pid, signal.SIGTERM)
                else:
                    process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    if os.name == "posix":
                        os.killpg(process.pid, signal.SIGKILL)
                    else:
                        process.kill()
                    process.wait()
                return WORKER_CANCELLED
            if time.monotonic() >= deadline:
                if os.name == "posix":
                    os.killpg(process.pid, signal.SIGKILL)
                else:
                    process.kill()
                process.wait()
                raise subprocess.TimeoutExpired(command, timeout)
            time.sleep(0.1)
        if cancel_event is not None and cancel_event.is_set():
            return WORKER_CANCELLED
        return int(process.returncode)


__all__ = [
    "WORKER_MODULE",
    "WORKER_THREAD_LIMIT",
    "WORKER_CANCELLED",
    "WORKER_TIMEOUT_SECONDS",
    "run_worker",
]
