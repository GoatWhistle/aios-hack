from __future__ import annotations

from backend.contexts.assistant.domain.errors import (
    SessionDiskError,
)

import json
import os
import re
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator, Mapping, Sequence
from backend.shared.settings import Settings
from backend.shared.paths import repository_root
from backend.contexts.assistant.domain.session_events import restore_exchanges

SESSIONS_ENV_VAR = "AIOS_JARVIS_SESSIONS"
OUT_ENV_VAR = "AIOS_OUT_DIR"
EVENTS_FILE = "events.jsonl"
META_FILE = "meta.json"
ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,80}$")
MAX_EVENTS = 4000
SESSION_TTL_ENV_VAR = "AIOS_JARVIS_SESSION_TTL_DAYS"
DEFAULT_SESSION_TTL_DAYS = 30
MAX_SESSION_TTL_DAYS = 3650


def now() -> str:
    return (
        datetime.now(tz=timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _repository_root() -> Path:
    return repository_root(Path.cwd())


def default_sessions_root(settings: Settings | None = None) -> Path:
    resolved = Settings.from_env() if settings is None else settings
    if resolved.jarvis_sessions is not None:
        return resolved.jarvis_sessions
    base = resolved.out_root if resolved.raw.get(OUT_ENV_VAR) else _repository_root() / "out"
    return base / "jarvis" / "sessions"


def check_id(session_id: str) -> str:
    text = str(session_id or "").strip()
    if not ID_PATTERN.match(text):
        raise SessionDiskError(
            f"session identifier {session_id!r} will not do as a directory name: "
            "Latin letters, digits, dot, hyphen and underscore are allowed, "
            "no longer than 80 characters"
        )
    return text


@dataclass
class Meta:
    session_id: str
    started: str
    last: str
    scenes: int = 0
    summary: str = ""
    first_question: str = ""
    lang: str = "ru"

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.session_id,
            "started": self.started,
            "last": self.last,
            "scenes": self.scenes,
            "summary": self.summary,
            "first_question": self.first_question,
            "lang": self.lang,
        }

    def as_row(self) -> dict[str, Any]:
        return {
            "id": self.session_id,
            "started": self.started,
            "last": self.last,
            "scenes": self.scenes,
            "first_question": self.first_question,
        }


def _read_meta(path: Path) -> Meta | None:
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    if not isinstance(loaded, dict):
        return None
    identifier = str(loaded.get("id") or path.parent.name)
    stamp = str(loaded.get("started") or now())
    return Meta(
        session_id=identifier,
        started=stamp,
        last=str(loaded.get("last") or stamp),
        scenes=int(loaded.get("scenes") or 0),
        summary=str(loaded.get("summary") or ""),
        first_question=str(loaded.get("first_question") or ""),
        lang=str(loaded.get("lang") or "ru"),
    )


class SessionDisk:
    def __init__(
        self,
        root: Path | str | None = None,
        retention_days: int | None = None,
    ) -> None:
        if retention_days is None:
            raw_ttl = os.environ.get(SESSION_TTL_ENV_VAR, "")
            try:
                retention_days = int(raw_ttl) if raw_ttl else DEFAULT_SESSION_TTL_DAYS
            except ValueError as error:
                raise SessionDiskError(
                    f"{SESSION_TTL_ENV_VAR} must be an integer from 1 to {MAX_SESSION_TTL_DAYS}"
                ) from error
        if retention_days < 1 or retention_days > MAX_SESSION_TTL_DAYS:
            raise SessionDiskError(
                f"{SESSION_TTL_ENV_VAR} must be an integer from 1 to {MAX_SESSION_TTL_DAYS}"
            )
        self._retention = timedelta(days=retention_days)
        self._root = Path(root) if root is not None else default_sessions_root()
        self._lock = threading.Lock()
        self._meta: dict[str, Meta] = {}
        self.reload()

    @property
    def root(self) -> Path:
        return self._root

    def reload(self) -> None:
        collected: dict[str, Meta] = {}
        cutoff = datetime.now(tz=timezone.utc) - self._retention
        if self._root.is_dir():
            for entry in sorted(self._root.iterdir()):
                if not entry.is_dir():
                    continue
                path = entry / META_FILE
                if not path.is_file():
                    continue
                meta = _read_meta(path)
                if meta is not None:
                    if self._is_expired(meta, cutoff):
                        self._delete_directory(entry)
                        continue
                    collected[meta.session_id] = meta
        with self._lock:
            self._meta = collected

    def count(self) -> int:
        self.prune_expired()
        with self._lock:
            return len(self._meta)

    def listing(self) -> list[dict[str, Any]]:
        self.prune_expired()
        with self._lock:
            rows = [meta.as_row() for meta in self._meta.values()]
        rows.sort(key=lambda row: str(row["last"]), reverse=True)
        return rows

    def meta(self, session_id: str) -> Meta | None:
        self.prune_expired()
        with self._lock:
            return self._meta.get(session_id)

    @staticmethod
    def _is_expired(meta: Meta, cutoff: datetime) -> bool:
        try:
            last = datetime.fromisoformat(meta.last.replace("Z", "+00:00"))
        except ValueError:
            return False
        if last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        return last < cutoff

    @staticmethod
    def _delete_directory(directory: Path) -> None:
        if not directory.is_dir():
            return
        for path in sorted(directory.iterdir(), reverse=True):
            try:
                if path.is_file():
                    path.unlink()
            except OSError:
                pass
        try:
            directory.rmdir()
        except OSError:
            pass

    def prune_expired(self) -> None:
        cutoff = datetime.now(tz=timezone.utc) - self._retention
        with self._lock:
            expired = [
                meta.session_id
                for meta in self._meta.values()
                if self._is_expired(meta, cutoff)
            ]
        for identifier in expired:
            try:
                self.remove(identifier)
            except SessionDiskError:
                continue

    def directory(self, session_id: str) -> Path:
        return self._root / check_id(session_id)

    def _ensure(self, session_id: str, lang: str) -> Meta:
        with self._lock:
            found = self._meta.get(session_id)
            if found is not None:
                return found
            stamp = now()
            created = Meta(
                session_id=session_id, started=stamp, last=stamp, lang=lang
            )
            self._meta[session_id] = created
            return created

    def _write_meta(self, meta: Meta) -> None:
        directory = self.directory(meta.session_id)
        try:
            directory.mkdir(parents=True, exist_ok=True)
            (directory / META_FILE).write_text(
                json.dumps(meta.as_dict(), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except OSError as error:
            raise SessionDiskError(
                f"the metadata of session {meta.session_id} cannot be written to "
                f"{directory}: {error}"
            ) from error

    def append(self, session_id: str, event: Mapping[str, Any], lang: str = "ru") -> None:
        identifier = check_id(session_id)
        meta = self._ensure(identifier, lang)
        directory = self.directory(identifier)
        try:
            directory.mkdir(parents=True, exist_ok=True)
            with (directory / EVENTS_FILE).open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(dict(event), ensure_ascii=False) + "\n")
        except OSError:
            return
        meta.last = now()
        if event.get("type") == "ask":
            meta.scenes += 1
            if not meta.first_question:
                meta.first_question = str(event.get("question") or "")[:200]
        self._write_meta(meta)

    def set_summary(self, session_id: str, summary: str) -> None:
        meta = self.meta(check_id(session_id))
        if meta is None:
            return
        meta.summary = summary
        meta.last = now()
        self._write_meta(meta)

    def events(self, session_id: str) -> list[dict[str, Any]]:
        directory = self.directory(session_id)
        path = directory / EVENTS_FILE
        if not path.is_file():
            raise SessionDiskError(
                f"session {session_id} is not on disk: the file {path} does not "
                "exist, there is nothing to show the history from"
            )
        collected: list[dict[str, Any]] = []
        try:
            with path.open("r", encoding="utf-8") as stream:
                for line in stream:
                    text = line.strip()
                    if not text:
                        continue
                    try:
                        loaded = json.loads(text)
                    except json.JSONDecodeError:
                        continue
                    if isinstance(loaded, dict):
                        collected.append(loaded)
                    if len(collected) >= MAX_EVENTS:
                        break
        except OSError as error:
            raise SessionDiskError(
                f"the events of session {session_id} cannot be read from {path}: {error}"
            ) from error
        return collected

    def remove(self, session_id: str) -> bool:
        identifier = check_id(session_id)
        directory = self.directory(identifier)
        with self._lock:
            existed = self._meta.pop(identifier, None) is not None
        if not directory.is_dir():
            return existed
        self._delete_directory(directory)
        return True

    def exchanges(self, session_id: str) -> Iterator[Mapping[str, Any]]:
        try:
            events = self.events(session_id)
        except SessionDiskError:
            return iter(())
        return iter(events)


__all__ = [
    "EVENTS_FILE",
    "META_FILE",
    "Meta",
    "SESSIONS_ENV_VAR",
    "SessionDisk",
    "SessionDiskError",
    "check_id",
    "default_sessions_root",
    "now",
    "restore_exchanges",
]
