from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import urllib.request

from backend.shared.env_file import load_env_file
from backend.contexts.assistant.infrastructure.artifacts.runs import RunStore


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the built AIOS console and Jarvis on one local origin.")
    parser.add_argument("--env-file", type=Path, default=ROOT / ".env.local")
    parser.add_argument("--web-port", type=int, default=5199)
    parser.add_argument("--api-port", type=int, default=8010)
    parser.add_argument("--runs-dir", type=Path, help="override recorded runs from the env file")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    os.chdir(ROOT)
    load_env_file(args.env_file)
    if args.runs_dir is not None:
        os.environ["AIOS_JARVIS_RUNS"] = str(args.runs_dir.resolve())
    for port in (args.web_port, args.api_port):
        if not 1 <= port <= 65535:
            parser.error("ports must be between 1 and 65535")
    if args.web_port == args.api_port:
        parser.error("web and API ports must differ")
    defaults = {
        "AIOS_PROJECT_ROOT": str(ROOT),
        "AIOS_UI_DATA": str(ROOT / "frontend/public/data"),
        "AIOS_JARVIS_RUNS": str(ROOT / "out/jarvis-evidence-20260926/runs"),
        "AIOS_JARVIS_WEB_RUNS": str(ROOT / "out/web-runs"),
        "AIOS_JARVIS_SESSIONS": str(ROOT / "out/jarvis/sessions"),
        "AIOS_JARVIS_DOCS": str(ROOT),
    }
    for name, value in defaults.items():
        os.environ.setdefault(name, value)
    os.environ["AIOS_JARVIS_UPSTREAM"] = f"http://127.0.0.1:{args.api_port}"
    required = [ROOT / "frontend/dist/index.html", Path(os.environ["AIOS_UI_DATA"]) / "scenarios.json"]
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        parser.error("Missing build/data: " + ", ".join(missing))
    if not RunStore().exists():
        parser.error("Recorded runs are missing at " + os.environ["AIOS_JARVIS_RUNS"]
                     + "; set AIOS_JARVIS_RUNS or --runs-dir to the installed evidence directory")
    check = subprocess.run([
        sys.executable, "-m", "backend.interfaces.cli.jarvis",
        "--env-file", str(args.env_file.resolve()), "--check",
    ], check=False)
    if check.returncode or args.check:
        return check.returncode
    commands = [
        [sys.executable, "-m", "backend.interfaces.cli.jarvis", "--env-file", str(args.env_file.resolve()),
         "--host", "127.0.0.1", "--port", str(args.api_port)],
        [sys.executable, "-m", "backend.interfaces.cli.web", "--host", "127.0.0.1",
         "--port", str(args.web_port), "--dist", str(ROOT / "frontend/dist")],
    ]
    children: list[subprocess.Popen] = []
    def stop(_signum, _frame):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, stop)
    try:
        for command in commands:
            children.append(subprocess.Popen(command))
        deadline = time.monotonic() + 30
        url = f"http://127.0.0.1:{args.web_port}"
        while time.monotonic() < deadline:
            if any(child.poll() is not None for child in children):
                raise RuntimeError("A service exited before becoming ready; inspect its message above")
            try:
                with urllib.request.urlopen(url + "/api/jarvis/health", timeout=2) as response:
                    if json.load(response).get("ok"):
                        break
            except (OSError, ValueError):
                pass
            time.sleep(0.25)
        else:
            raise RuntimeError("The local proxy did not become ready within 30 seconds")
        print(f"Jarvis ready: {url} (model connectivity is checked by a real question)", flush=True)
        while all(child.poll() is None for child in children):
            time.sleep(0.25)
        return 1
    except KeyboardInterrupt:
        return 0
    finally:
        for child in children:
            if child.poll() is None:
                child.terminate()
        for child in children:
            try:
                child.wait(timeout=10)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait()


if __name__ == "__main__":
    raise SystemExit(main())
