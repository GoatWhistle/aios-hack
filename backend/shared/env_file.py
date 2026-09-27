"""Load literal dotenv assignments without shell evaluation or overriding exports."""
from __future__ import annotations

import os
import re
import shlex
from pathlib import Path


def load_env_file(path: Path) -> None:
    if not path.is_file():
        raise FileNotFoundError(f"Environment file not found: {path}")
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        line = line.removeprefix("export ").strip()
        name, separator, raw = line.partition("=")
        name = name.strip()
        if not separator or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
            raise ValueError(f"Invalid environment assignment at {path.name}:{number}")
        try:
            words = shlex.split(raw, comments=True, posix=True)
        except ValueError:
            raise ValueError(f"Invalid environment quoting at {path.name}:{number}") from None
        if len(words) > 1:
            raise ValueError(f"Quote environment values containing spaces at {path.name}:{number}")
        os.environ.setdefault(name, words[0] if words else "")
