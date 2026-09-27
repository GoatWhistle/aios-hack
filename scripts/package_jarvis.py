from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import tarfile


ROOT = Path(__file__).resolve().parents[1]
SOURCES = (
    "backend", "frontend/dist", "frontend/public/data", "frontend/public/jarvis/knowledge",
    "config", "deploy", "scripts/jarvis_stack.py", "scripts/import_jarvis_evidence.py",
    "pyproject.toml", "requirements-ml.txt", "README.md", "ARCHITECTURE.md",
    "JARVIS_DEPLOY.md", "JARVIS_DEMO_RUNBOOK.md", "JARVIS_CONTEXT.md",
    "PROJECT_CONTEXT.md", "JARVIS_STATUS_20260927.md", "JARVIS_BACKLOG.md",
    "artifacts/jarvis-scenario-registry.json",
    "artifacts/surrogate-trajectory-ab-20260910/final-submission",
    "out/jarvis-evidence-20260926/runs",
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Package the console, Jarvis and recorded evidence without secrets or sessions.")
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    files: dict[str, Path] = {}
    for source in SOURCES:
        base = ROOT / source
        if not base.exists():
            parser.error(f"Required release input is missing: {source}")
        for path in ([base] if base.is_file() else sorted(base.rglob("*"))):
            relative = path.relative_to(ROOT)
            if not path.is_file() or path.is_symlink():
                continue
            if "__pycache__" in relative.parts or path.suffix == ".pyc" or path.name.startswith(".env"):
                continue
            if "/opm/runs/" in relative.as_posix() or "/opm/cache/" in relative.as_posix():
                continue
            files[relative.as_posix()] = path
    output = args.output.resolve()
    if output.exists():
        parser.error("Output already exists; choose a new release filename")
    if str(output).startswith(str(ROOT / "frontend")):
        parser.error("Write release archives outside the public frontend")
    manifest = {
        "format": "aios.jarvis-release.v1",
        "files": {name: hashlib.sha256(path.read_bytes()).hexdigest() for name, path in sorted(files.items())},
        "excluded": ["API keys", "session history", "surrogate runtime", "OPM binary outputs"],
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(output, "w:gz") as archive:
        for name, path in sorted(files.items()):
            archive.add(path, arcname=name, recursive=False)
    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    manifest["archive_sha256"] = digest
    output.with_suffix(output.suffix + ".manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"Packaged {len(files)} files: {output.name}, {output.stat().st_size} bytes, sha256={digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
