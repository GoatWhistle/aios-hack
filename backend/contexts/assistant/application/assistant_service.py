from __future__ import annotations

import time
import re
import logging
import os
import threading
from typing import Any, Callable, Mapping

from backend.contexts.assistant.infrastructure.artifacts import ArtifactStore
from backend.contexts.assistant.infrastructure.artifacts import RunStore, RunError
from backend.contexts.assistant.infrastructure.docs_index import (
    DocsIndex,
    DocsIndexError,
    load_index,
)
from backend.contexts.assistant.infrastructure.knowledge import Knowledge
from backend.contexts.assistant.application.briefing_cache import BRIEFING_TTL, BriefingCache
from backend.contexts.assistant.application.orchestrator import Event, Orchestrator
from backend.contexts.assistant.domain.session import SessionStore
from backend.contexts.assistant.infrastructure.session_store import SessionDisk, SessionDiskError
from backend.contexts.assistant.infrastructure.stt import SttEngine
from backend.contexts.assistant.infrastructure.system_map import SystemMap, SystemMapError
from backend.contexts.assistant.infrastructure.tts import TtsEngine, default_voice
from backend.contexts.assistant.application.tools.context import ConsoleContext
from backend.contexts.assistant.infrastructure.llm.provider import NoApiKeyError, build_client
from backend.shared.settings import Settings

DEFAULT_PORT = 8010
DEFAULT_HOST = "0.0.0.0"
DEV_ORIGINS: tuple[str, ...] = (
    "http://localhost:5199",
    "http://127.0.0.1:5199",
)
MAX_BODY_BYTES = 16 * 1024
MAX_AUDIO_BYTES = 2 * 1024 * 1024
AUDIO_ROUTE = "/api/jarvis/transcribe"
MAX_CONCURRENT_REQUESTS_ENV = "JARVIS_MAX_CONCURRENT_REQUESTS"
DEFAULT_MAX_CONCURRENT_REQUESTS = 8
HARD_MAX_CONCURRENT_REQUESTS = 64


class JarvisService:
    def __init__(
        self,
        store: ArtifactStore | None = None,
        knowledge: Knowledge | None = None,
        env: Mapping[str, str] | None = None,
        orchestrator: Orchestrator | None = None,
        docs: DocsIndex | None = None,
        system: SystemMap | None = None,
        disk: SessionDisk | None = None,
        tts: TtsEngine | None = None,
        stt: SttEngine | None = None,
        runs: RunStore | None = None,
        clock: Callable[[], float] = time.monotonic,
        max_concurrent_requests: int | None = None,
    ) -> None:
        if max_concurrent_requests is None:
            source = os.environ if env is None else env
            raw_limit = source.get(MAX_CONCURRENT_REQUESTS_ENV, "")
            try:
                max_concurrent_requests = (
                    int(raw_limit) if raw_limit else DEFAULT_MAX_CONCURRENT_REQUESTS
                )
            except ValueError as error:
                raise ValueError(
                    f"{MAX_CONCURRENT_REQUESTS_ENV} must be an integer from 1 to "
                    f"{HARD_MAX_CONCURRENT_REQUESTS}"
                ) from error
        if not 1 <= max_concurrent_requests <= HARD_MAX_CONCURRENT_REQUESTS:
            raise ValueError(
                f"{MAX_CONCURRENT_REQUESTS_ENV} must be an integer from 1 to "
                f"{HARD_MAX_CONCURRENT_REQUESTS}"
            )
        self._store = store if store is not None else ArtifactStore()
        self._knowledge = knowledge if knowledge is not None else Knowledge()
        self._client_error: str | None = None
        self._orchestrator = orchestrator
        self._clock = clock
        self._request_lock = threading.Lock()
        self._last_request: dict[str, Any] | None = None
        self._max_concurrent_requests = max_concurrent_requests
        self._active_requests = 0
        self._docs_error: str | None = None
        self._system_error: str | None = None
        self._docs = docs if docs is not None else self._load_docs()
        self._system = system if system is not None else self._load_system()
        self._disk = disk if disk is not None else self._load_disk()
        self._sessions = (
            orchestrator.sessions
            if orchestrator is not None
            else SessionStore(disk=self._disk)
        )
        self._env = env
        self._runs = runs
        self._tts = tts if tts is not None else TtsEngine()
        self._stt = stt if stt is not None else SttEngine(env)
        self._briefings = BriefingCache(self._clock, BRIEFING_TTL)
        if orchestrator is None:
            self._build()

    def _load_docs(self) -> DocsIndex | None:
        try:
            return load_index()
        except (DocsIndexError, OSError) as error:
            self._docs_error = str(error)
            return None

    def _load_system(self) -> SystemMap | None:
        try:
            return SystemMap()
        except SystemMapError as error:
            self._system_error = str(error)
            return None

    def _load_disk(self) -> SessionDisk | None:
        try:
            return SessionDisk()
        except (SessionDiskError, OSError):
            return None

    def _build(self) -> None:
        try:
            client = build_client(self._env)
        except NoApiKeyError as error:
            self._client_error = str(error)
            return
        self._orchestrator = Orchestrator(
            client=client,
            store=self._store,
            runs=self._runs,
            knowledge=self._knowledge,
            sessions=self._sessions,
            docs=self._docs,
            system=self._system,
            disk=self._disk,
            capabilities=self.capabilities,
        )

    @property
    def sessions(self) -> SessionStore:
        return self._sessions

    @property
    def disk(self) -> SessionDisk | None:
        return self._disk

    @property
    def tts(self) -> TtsEngine:
        return self._tts

    @property
    def stt(self) -> SttEngine:
        return self._stt

    @property
    def available(self) -> bool:
        return self._orchestrator is not None

    @property
    def orchestrator(self) -> Orchestrator:
        if self._orchestrator is None:
            raise NoApiKeyError(self._client_error or "no chat client configured")
        return self._orchestrator

    def capabilities(self) -> dict[str, Any]:
        return {
            "tts": self._tts.available,
            "stt": "server" if self._stt.available else "none",
            "docs": self._docs.size() if self._docs is not None else 0,
            "sessions": self._disk.count() if self._disk is not None else 0,
        }

    def health(self) -> tuple[int, dict[str, Any]]:
        data_ready = bool(self._store.scenarios())
        with self._request_lock:
            active_requests = self._active_requests
        model: dict[str, Any] = {
            "configured": self.available,
            "connectivity": "unverified" if self.available else "unavailable",
        }
        if self.available:
            model.update(
                provider=self._orchestrator.provider,
                name=self._orchestrator.model,
            )
        body: dict[str, Any] = {
            "data": self._store.scenario().provenance(),
            "scenarios": list(self._store.scenarios()),
            "knowledge": {
                "terms": self._knowledge.term_count,
                "screens": self._knowledge.screen_count,
                "system_nodes": (
                    self._system.node_count if self._system is not None else 0
                ),
            },
            **self.capabilities(),
            "voice": {
                "tts_voice_ru": default_voice("ru"),
                "tts_voice_en": default_voice("en"),
                "stt_model": self._stt.model,
            },
            "readiness": {
                "data": {"ready": data_ready, "scenario_count": len(self._store.scenarios())},
                "model": model,
                "requests": {
                    "active": active_requests,
                    "limit": self._max_concurrent_requests,
                },
            },
            "last_request": self.last_request(),
        }
        if self._docs_error is not None:
            body["docs_error"] = self._docs_error
        if self._system_error is not None:
            body["system_error"] = self._system_error
        if self._orchestrator is None:
            body["ok"] = False
            body["error"] = "no-api-key"
            body["message"] = self._client_error or "no chat client configured"
            return 503, body
        body["ok"] = True
        body["provider"] = self._orchestrator.provider
        body["model"] = self._orchestrator.model
        return 200, body

    def last_request(self) -> dict[str, Any] | None:
        with self._request_lock:
            return None if self._last_request is None else dict(self._last_request)

    def try_acquire_request(self) -> bool:
        with self._request_lock:
            if self._active_requests >= self._max_concurrent_requests:
                return False
            self._active_requests += 1
            return True

    def release_request(self) -> None:
        with self._request_lock:
            self._active_requests = max(0, self._active_requests - 1)

    def record_request(
        self,
        request_id: str,
        duration_ms: int,
        outcome: str,
        error_code: str | None = None,
        http_status: int | None = None,
    ) -> None:
        provider = self._orchestrator.provider if self.available else None
        model_name = self._orchestrator.model if self.available else None
        record = {
            "request_id": request_id,
            "duration_ms": max(0, int(duration_ms)),
            "provider": provider,
            "model": model_name,
            "outcome": outcome,
            "error_code": error_code,
            "http_status": http_status,
        }
        with self._request_lock:
            self._last_request = record
        logging.getLogger("jarvis.request").info(
            "request_id=%s duration_ms=%d provider=%s model=%s outcome=%s error_code=%s http_status=%s",
            request_id,
            record["duration_ms"],
            provider or "unavailable",
            model_name or "unavailable",
            outcome,
            error_code or "none",
            http_status or "none",
        )

    def session_rows(self) -> list[dict[str, Any]]:
        if self._disk is None:
            return []
        return self._disk.listing()

    def run_artifact(self, run_id: str, name: str) -> bytes:
        """Read one explicitly allow-listed JSON artifact from a manifest-backed run."""
        store = self._runs if self._runs is not None else RunStore()

        def read_record() -> Any:
            try:
                return store.read(run_id)
            except RunError:
                settings = Settings.from_env(self._env)
                web_root = settings.jarvis_web_runs or (
                    settings.out_root / "web-runs"
                    if settings.raw.get("AIOS_OUT_DIR")
                    else settings.project_root / "out" / "web-runs"
                )
                if web_root == store.root:
                    raise
                return RunStore(web_root).read(run_id)

        artifacts = {
            "manifest": "manifest.json",
            "validation": "validation/result.json",
            "constraints": "validation/constraints_report.json",
            "economics": "economics/result.json",
            "npv-table": "economics/npv-table.json",
            "submission": "submission/claimed_npv.json",
            "physics": "validation/physics-report.json",
        }
        relative = artifacts.get(name)
        if name == "opm-response":
            record = read_record()
            schedule_hash = record.manifest.get("schedule_hash")
            if not isinstance(schedule_hash, str) or re.fullmatch(r"[0-9a-f]{64}", schedule_hash) is None:
                raise RunError(f"run {run_id!r} has no valid recorded schedule hash for its OPM response")
            path = record.directory / "observation" / schedule_hash / "response.json"
            max_bytes = 16 * 1024 * 1024
        elif relative is None:
            raise RunError(f"run artifact {name!r} is not an allowed source")
        else:
            record = read_record()
            if name == "physics":
                candidates = sorted((record.directory / "validation").glob("physics*.json"))
                path = candidates[0] if candidates else record.directory / relative
            else:
                path = record.directory / relative
            max_bytes = 4 * 1024 * 1024
        if not path.resolve().is_relative_to(record.directory.resolve()):
            raise RunError(f"run artifact {name!r} resolves outside its run directory")
        if not path.is_file():
            raise RunError(f"run {run_id!r} has no recorded {name} artifact")
        content = path.read_bytes()
        if len(content) > max_bytes:
            raise RunError(f"run artifact {name} exceeds the {max_bytes // (1024 * 1024)} MiB read limit")
        return content

    def session_events(self, session_id: str) -> list[dict[str, Any]]:
        if self._disk is None:
            raise SessionDiskError(
                "the on-disk session store did not come up: there is nowhere to show the "
                "history from"
            )
        return self._disk.events(session_id)

    def remove_session(self, session_id: str) -> bool:
        if self._disk is None:
            return False
        removed = self._disk.remove(session_id)
        self._sessions.forget(session_id)
        return removed

    def briefing(
        self, session_id: str, console: ConsoleContext
    ) -> list[dict[str, Any]]:
        key = (console.scenario, console.step or -1, console.lang)
        cached = self._briefings.get(key)
        if cached is not None:
            return cached
        events = [
            event.as_dict()
            for event in self.orchestrator.briefing(session_id, console)
        ]
        return self._briefings.put(key, events)


def console_context(payload: Mapping[str, Any]) -> ConsoleContext:
    raw = payload.get("context") or {}
    step = raw.get("step")
    return ConsoleContext(
        scenario=str(raw.get("scenario") or "base"),
        step=int(step) if isinstance(step, int) else None,
        date=str(raw["date"]) if raw.get("date") else None,
        selected_well=str(raw["selected_well"]) if raw.get("selected_well") else None,
        run_id=str(raw["run_id"]) if raw.get("run_id") else None,
        context_version=str(raw["context_version"]) if raw.get("context_version") else None,
        workspace=str(raw["workspace"]) if raw.get("workspace") else None,
        view=str(raw["view"]) if raw.get("view") else None,
        lang=str(payload.get("lang") or "ru"),
    )


def query_context(params: Mapping[str, list[str]]) -> ConsoleContext:
    def first(name: str) -> str | None:
        values = params.get(name)
        return values[0] if values else None

    raw_step = first("step")
    step: int | None = None
    if raw_step is not None:
        try:
            step = int(raw_step)
        except ValueError:
            step = None
    return ConsoleContext(
        scenario=first("scenario") or "base",
        step=step,
        date=first("date"),
        selected_well=first("well"),
        run_id=first("run_id"),
        context_version=first("context_version"),
        workspace=first("workspace"),
        view=first("view"),
        lang=first("lang") or "ru",
    )


__all__ = [
    "AUDIO_ROUTE",
    "BRIEFING_TTL",
    "DEFAULT_HOST",
    "DEFAULT_PORT",
    "DEV_ORIGINS",
    "Event",
    "JarvisService",
    "MAX_AUDIO_BYTES",
    "MAX_BODY_BYTES",
    "console_context",
    "query_context",
]
