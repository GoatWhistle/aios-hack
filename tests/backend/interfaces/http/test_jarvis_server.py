from __future__ import annotations

import io
import json
import threading
import time
from contextlib import contextmanager
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from typing import Any, Iterator

import pytest

from backend.contexts.assistant.infrastructure.artifacts import ArtifactStore, RunStore
from backend.contexts.assistant.domain.errors import UpstreamError
from backend.contexts.assistant.infrastructure.knowledge import Knowledge
from backend.contexts.assistant.application.orchestrator import Orchestrator
from backend.contexts.assistant.domain.session import SessionStore
from backend.contexts.assistant.infrastructure.session_store import SessionDisk
from backend.contexts.assistant.infrastructure.llm.chat_events import ToolCall
from backend.contexts.assistant.infrastructure.llm.fake_chat import FakeChatClient
from backend.contexts.assistant.application.tools import HANDLERS
from backend.interfaces.http.kit import sse
from backend.interfaces.http.assistant.server import build_handler
from backend.contexts.assistant.application.assistant_service import JarvisService
from backend.interfaces.http.kit.sse import chunk, encode_event, error_event

CALL = ToolCall(id="c1", name="field_metrics", args={"step": 96})
CAPTION = "Фонд работает штатно."


def repo_root() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "frontend" / "public" / "data").is_dir():
            return parent
    raise RuntimeError("repository root with frontend/public/data was not found")


@pytest.fixture(scope="module")
def store() -> ArtifactStore:
    return ArtifactStore(repo_root() / "frontend" / "public" / "data")


@pytest.fixture(scope="module")
def knowledge() -> Knowledge:
    return Knowledge(repo_root() / "frontend" / "public" / "jarvis" / "knowledge")


def make_service(
    store: ArtifactStore,
    knowledge: Knowledge,
    with_key: bool,
    max_concurrent_requests: int = 8,
) -> JarvisService:
    if not with_key:
        return JarvisService(
            store=store,
            knowledge=knowledge,
            env={},
            max_concurrent_requests=max_concurrent_requests,
        )
    client = FakeChatClient(rounds=[[CALL]], caption=CAPTION, model="fake/recorded")
    orchestrator = Orchestrator(
        client=client, store=store, knowledge=knowledge, sessions=SessionStore()
    )
    return JarvisService(
        store=store,
        knowledge=knowledge,
        env={},
        orchestrator=orchestrator,
        max_concurrent_requests=max_concurrent_requests,
    )


def run(service: JarvisService) -> Iterator[str]:
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), build_handler(service))
    httpd.daemon_threads = True
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    host, port = httpd.server_address[0], httpd.server_address[1]
    try:
        yield f"http://{host}:{port}"
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=5)


@pytest.fixture()
def live(store: ArtifactStore, knowledge: Knowledge) -> Iterator[str]:
    yield from run(make_service(store, knowledge, with_key=True))


@pytest.fixture()
def keyless(store: ArtifactStore, knowledge: Knowledge) -> Iterator[str]:
    yield from run(make_service(store, knowledge, with_key=False))


def post(url: str, body: dict[str, Any]) -> urllib.request.addinfourl:
    request = urllib.request.Request(
        url,
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    return urllib.request.urlopen(request, timeout=10)


def read_events(response: urllib.request.addinfourl) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for raw in response:
        line = raw.decode("utf-8").strip()
        if line.startswith("data:"):
            events.append(json.loads(line[len("data:") :].strip()))
    return events


def test_health_reports_provider_and_knowledge(live: str) -> None:
    with urllib.request.urlopen(f"{live}/api/jarvis/health", timeout=5) as response:
        assert response.status == 200
        body = json.loads(response.read().decode("utf-8"))
    assert body["ok"] is True
    assert body["provider"] == "fake"
    assert body["model"] == "fake/recorded"
    assert body["data"] == "model-z-base-run"
    assert body["knowledge"]["terms"] >= 40
    assert body["knowledge"]["screens"] == 11
    assert body["readiness"]["data"]["ready"] is True
    assert body["readiness"]["model"]["configured"] is True
    assert body["readiness"]["model"]["connectivity"] == "unverified"
    assert body["readiness"]["requests"] == {"active": 0, "limit": 8}


def test_run_artifact_route_reads_only_allowlisted_manifest(tmp_path: Path, store: ArtifactStore, knowledge: Knowledge) -> None:
    runs_root = tmp_path / "runs"
    run_dir = runs_root / "artifact-test"
    run_dir.mkdir(parents=True)
    manifest = {"run_id": "artifact-test", "status": "rejected"}
    (run_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    service = JarvisService(store=store, knowledge=knowledge, env={}, runs=RunStore(runs_root))

    with contextmanager(run)(service) as url:
        with urllib.request.urlopen(f"{url}/api/jarvis/run-artifacts/artifact-test/manifest", timeout=5) as response:
            assert response.status == 200
            assert json.loads(response.read().decode("utf-8")) == manifest
        with pytest.raises(urllib.error.HTTPError) as error:
            urllib.request.urlopen(f"{url}/api/jarvis/run-artifacts/artifact-test/secret", timeout=5)
    assert error.value.code == 404


def test_opm_response_artifact_is_resolved_from_recorded_schedule_hash(
    tmp_path: Path, store: ArtifactStore, knowledge: Knowledge
) -> None:
    runs_root = tmp_path / "runs"
    schedule_hash = "a" * 64
    run_dir = runs_root / "response-test"
    run_dir.mkdir(parents=True)
    (run_dir / "manifest.json").write_text(
        json.dumps({"run_id": "response-test", "status": "verified", "schedule_hash": schedule_hash}),
        encoding="utf-8",
    )
    observation = run_dir / "observation" / schedule_hash
    observation.mkdir(parents=True)
    expected = {"interval_response": [{"well": "W1", "control_step": 2}]}
    (observation / "response.json").write_text(json.dumps(expected), encoding="utf-8")
    service = JarvisService(store=store, knowledge=knowledge, env={}, runs=RunStore(runs_root))

    with contextmanager(run)(service) as url:
        with urllib.request.urlopen(
            f"{url}/api/jarvis/run-artifacts/response-test/opm-response", timeout=5
        ) as response:
            assert json.loads(response.read().decode("utf-8")) == expected


def test_health_without_key_is_503(keyless: str) -> None:
    with pytest.raises(urllib.error.HTTPError) as error:
        urllib.request.urlopen(f"{keyless}/api/jarvis/health", timeout=5)
    assert error.value.code == 503
    body = json.loads(error.value.read().decode("utf-8"))
    assert body["ok"] is False
    assert body["error"] == "no-api-key"
    assert body["knowledge"]["terms"] >= 40
    assert body["readiness"]["model"]["configured"] is False
    assert body["readiness"]["model"]["connectivity"] == "unavailable"


def test_concurrency_limit_is_configurable_and_bounded(
    store: ArtifactStore, knowledge: Knowledge
) -> None:
    service = JarvisService(
        store=store,
        knowledge=knowledge,
        env={"JARVIS_MAX_CONCURRENT_REQUESTS": "3"},
    )
    _, health = service.health()
    assert health["readiness"]["requests"]["limit"] == 3
    with pytest.raises(ValueError, match="JARVIS_MAX_CONCURRENT_REQUESTS"):
        JarvisService(
            store=store,
            knowledge=knowledge,
            env={"JARVIS_MAX_CONCURRENT_REQUESTS": "65"},
        )


def test_ask_without_key_is_503(keyless: str) -> None:
    with pytest.raises(urllib.error.HTTPError) as error:
        post(
            f"{keyless}/api/jarvis/ask",
            {"session_id": "s", "question": "что с фондом"},
        )
    assert error.value.code == 503
    body = json.loads(error.value.read().decode("utf-8"))
    assert body["error"] == "no-api-key"


def test_ask_streams_the_contract_order(live: str) -> None:
    response = post(
        f"{live}/api/jarvis/ask",
        {
            "session_id": "s-live",
            "question": "что с фондом",
            "lang": "ru",
            "context": {"scenario": "base", "step": 96, "workspace": "overview", "view": "fund"},
        },
    )
    assert response.headers["Content-Type"].startswith("text/event-stream")
    events = read_events(response)
    kinds = [event["type"] for event in events]
    assert kinds[0] == "scene"
    assert kinds[-1] == "done"
    assert "card" in kinds
    assert "caption" in kinds
    assert "suggestions" in kinds
    card = next(event for event in events if event["type"] == "card")
    assert card["card"]["type"] == "metric"
    assert card["card"]["provenance"] == "model-z-base-run"
    caption = next(event for event in events if event["type"] == "caption")
    assert caption["text"] == CAPTION
    assert caption["guarded"] is True
    request_id = events[0]["request_id"]
    assert request_id
    assert all(event["request_id"] == request_id for event in events)
    with urllib.request.urlopen(f"{live}/api/jarvis/health", timeout=5) as health_response:
        health = json.loads(health_response.read().decode("utf-8"))
    assert health["last_request"] == {
        "request_id": request_id,
        "duration_ms": health["last_request"]["duration_ms"],
        "provider": "fake",
        "model": "fake/recorded",
        "outcome": "success",
        "error_code": None,
        "http_status": None,
    }


def test_provider_error_code_reaches_sse_and_health(
    store: ArtifactStore, knowledge: Knowledge
) -> None:
    class RateLimitedClient(FakeChatClient):
        def stream(self, *args: Any, **kwargs: Any) -> Any:
            raise UpstreamError(
                "provider rate limit", code="provider-rate-limit", http_status=429
            )

    orchestrator = Orchestrator(
        client=RateLimitedClient(rounds=[], caption="unused"),
        store=store,
        knowledge=knowledge,
        sessions=SessionStore(),
    )
    service = JarvisService(
        store=store, knowledge=knowledge, env={}, orchestrator=orchestrator
    )
    with contextmanager(run)(service) as url:
        events = read_events(
            post(
                f"{url}/api/jarvis/ask",
                {"session_id": "rate-limit", "question": "что с фондом"},
            )
        )
        failure = next(event for event in events if event["type"] == "error")
        assert failure["code"] == "provider-rate-limit"
        assert failure["http_status"] == 429
        assert failure["request_id"] == events[0]["request_id"]
        with urllib.request.urlopen(f"{url}/api/jarvis/health", timeout=5) as response:
            health = json.loads(response.read().decode("utf-8"))
        assert health["last_request"]["outcome"] == "error"
        assert health["last_request"]["error_code"] == "provider-rate-limit"
        assert health["last_request"]["http_status"] == 429


def test_busy_server_rejects_request_and_releases_capacity(
    store: ArtifactStore, knowledge: Knowledge
) -> None:
    service = make_service(
        store, knowledge, with_key=True, max_concurrent_requests=1
    )
    assert service.try_acquire_request() is True
    with contextmanager(run)(service) as url:
        with pytest.raises(urllib.error.HTTPError) as error:
            post(
                f"{url}/api/jarvis/ask",
                {"session_id": "over-capacity", "question": "что с фондом"},
            )
        assert error.value.code == 429
        body = json.loads(error.value.read().decode("utf-8"))
        assert body["error"] == "busy"
        with pytest.raises(urllib.error.HTTPError) as briefing_error:
            urllib.request.urlopen(
                f"{url}/api/jarvis/briefing?scenario=base&step=96", timeout=5
            )
        assert briefing_error.value.code == 429
        assert json.loads(briefing_error.value.read().decode("utf-8"))["error"] == "busy"
        service.release_request()
        events = read_events(
            post(
                f"{url}/api/jarvis/ask",
                {"session_id": "after-capacity", "question": "что с фондом"},
            )
        )
        assert events[-1]["type"] == "done"
        with urllib.request.urlopen(f"{url}/api/jarvis/health", timeout=5) as response:
            health = json.loads(response.read().decode("utf-8"))
        assert health["readiness"]["requests"] == {"active": 0, "limit": 1}


def test_response_timeout_is_reported_and_releases_request_slot(
    store: ArtifactStore, knowledge: Knowledge
) -> None:
    elapsed = [0.0]

    class SlowClient(FakeChatClient):
        def stream(self, *args: Any, **kwargs: Any) -> Any:
            elapsed[0] = 2.0
            yield CALL

    orchestrator = Orchestrator(
        client=SlowClient(rounds=[], caption=CAPTION),
        store=store,
        knowledge=knowledge,
        sessions=SessionStore(),
        timeout=1.0,
        clock=lambda: elapsed[0],
    )
    service = JarvisService(
        store=store,
        knowledge=knowledge,
        env={},
        orchestrator=orchestrator,
        max_concurrent_requests=1,
    )
    with contextmanager(run)(service) as url:
        events = read_events(
            post(
                f"{url}/api/jarvis/ask",
                {"session_id": "timeout-live", "question": "что с фондом"},
            )
        )
        failure = next(event for event in events if event["type"] == "error")
        assert failure["code"] == "timeout"
        with urllib.request.urlopen(f"{url}/api/jarvis/health", timeout=5) as response:
            health = json.loads(response.read().decode("utf-8"))
        assert health["readiness"]["requests"] == {"active": 0, "limit": 1}
        assert health["last_request"]["error_code"] == "timeout"


def test_deadline_inside_sync_tool_reaches_sse_and_releases_request_slot(
    store: ArtifactStore,
    knowledge: Knowledge,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def slow_tool(context: Any, _arguments: Any) -> None:
        while True:
            context.check_cancelled()
            time.sleep(0.005)

    monkeypatch.setitem(HANDLERS, "field_metrics", slow_tool)
    orchestrator = Orchestrator(
        client=FakeChatClient(rounds=[[CALL]], caption=CAPTION),
        store=store,
        knowledge=knowledge,
        sessions=SessionStore(),
        timeout=0.15,
    )
    service = JarvisService(
        store=store,
        knowledge=knowledge,
        env={},
        orchestrator=orchestrator,
        max_concurrent_requests=1,
    )
    with contextmanager(run)(service) as url:
        events = read_events(
            post(
                f"{url}/api/jarvis/ask",
                {"session_id": "tool-timeout-live", "question": "что с фондом"},
            )
        )
        failure = next(event for event in events if event["type"] == "error")
        assert failure["code"] == "timeout"
        assert not any(event["type"] == "card" for event in events)
        with urllib.request.urlopen(f"{url}/api/jarvis/health", timeout=5) as response:
            health = json.loads(response.read().decode("utf-8"))
        assert health["readiness"]["requests"] == {"active": 0, "limit": 1}
        assert health["last_request"]["error_code"] == "timeout"


def test_session_history_is_readable_after_service_restart(
    tmp_path: Path, store: ArtifactStore, knowledge: Knowledge
) -> None:
    sessions_root = tmp_path / "jarvis-sessions"

    def build_service(disk: SessionDisk) -> JarvisService:
        orchestrator = Orchestrator(
            client=FakeChatClient(rounds=[[CALL]], caption=CAPTION),
            store=store,
            knowledge=knowledge,
            sessions=SessionStore(disk=disk),
            disk=disk,
        )
        return JarvisService(
            store=store,
            knowledge=knowledge,
            env={},
            orchestrator=orchestrator,
            disk=disk,
        )

    first_disk = SessionDisk(sessions_root)
    with contextmanager(run)(build_service(first_disk)) as first_url:
        events = read_events(
            post(
                f"{first_url}/api/jarvis/ask",
                {"session_id": "restart-check", "question": "что с фондом"},
            )
        )
        assert events[-1]["type"] == "done"

    restarted_service = build_service(SessionDisk(sessions_root))
    with contextmanager(run)(restarted_service) as restarted_url:
        with urllib.request.urlopen(
            f"{restarted_url}/api/jarvis/sessions/restart-check", timeout=5
        ) as response:
            saved = json.loads(response.read().decode("utf-8"))
        assert saved["id"] == "restart-check"
        assert any(event.get("type") == "caption" for event in saved["events"])
        assert any(event.get("type") == "done" for event in saved["events"])
        with urllib.request.urlopen(
            f"{restarted_url}/api/jarvis/health", timeout=5
        ) as response:
            health = json.loads(response.read().decode("utf-8"))
        assert health["data"] == "model-z-base-run"


def test_ask_rejects_an_empty_question(live: str) -> None:
    response = post(f"{live}/api/jarvis/ask", {"session_id": "s2", "question": ""})
    events = read_events(response)
    assert events[-1]["type"] == "error"
    assert events[-1]["code"] == "bad-request"


def test_cancel_marks_the_session(live: str) -> None:
    response = post(f"{live}/api/jarvis/cancel", {"session_id": "s-cancel"})
    body = json.loads(response.read().decode("utf-8"))
    assert body["session_id"] == "s-cancel"


def test_cancel_interrupts_client_stream_and_frees_request_slot(
    store: ArtifactStore, knowledge: Knowledge
) -> None:
    entered = threading.Event()
    cancelled = threading.Event()

    class CancellableClient(FakeChatClient):
        def stream(
            self,
            messages: Any,
            tools: Any,
            system: str,
            cancellation: Any = None,
        ) -> Any:
            def generate() -> Any:
                entered.set()
                unregister = cancellation.register(cancelled.set)
                try:
                    if cancelled.wait(3):
                        raise UpstreamError("request cancelled", code="cancelled")
                    yield from super(CancellableClient, self).stream(
                        messages, tools, system, cancellation
                    )
                finally:
                    unregister()

            return generate()

    orchestrator = Orchestrator(
        client=CancellableClient(rounds=[[CALL]], caption=CAPTION),
        store=store,
        knowledge=knowledge,
        sessions=SessionStore(),
    )
    service = JarvisService(
        store=store,
        knowledge=knowledge,
        env={},
        orchestrator=orchestrator,
        max_concurrent_requests=1,
    )
    with contextmanager(run)(service) as url:
        events: list[dict[str, Any]] = []
        request_thread = threading.Thread(
            target=lambda: events.extend(
                read_events(
                    post(
                        f"{url}/api/jarvis/ask",
                        {"session_id": "cancel-live", "question": "что с фондом"},
                    )
                )
            ),
            daemon=True,
        )
        request_thread.start()
        assert entered.wait(2)
        cancel_response = post(
            f"{url}/api/jarvis/cancel", {"session_id": "cancel-live"}
        )
        assert json.loads(cancel_response.read().decode("utf-8"))["cancelled"] is True
        request_thread.join(timeout=2)
        assert not request_thread.is_alive()
        assert cancelled.is_set()
        assert not any(event["type"] == "card" for event in events)
        assert events[-1]["type"] == "error"
        assert events[-1]["code"] == "cancelled"
        with urllib.request.urlopen(f"{url}/api/jarvis/health", timeout=5) as response:
            health = json.loads(response.read().decode("utf-8"))
        assert health["readiness"]["requests"] == {"active": 0, "limit": 1}


def test_unknown_route_is_404(live: str) -> None:
    with pytest.raises(urllib.error.HTTPError) as error:
        urllib.request.urlopen(f"{live}/api/jarvis/nope", timeout=5)
    assert error.value.code == 404


def test_cors_allows_the_dev_origin(live: str) -> None:
    request = urllib.request.Request(
        f"{live}/api/jarvis/health", headers={"Origin": "http://localhost:5199"}
    )
    with urllib.request.urlopen(request, timeout=5) as response:
        assert (
            response.headers["Access-Control-Allow-Origin"]
            == "http://localhost:5199"
        )


def test_cors_is_absent_for_a_foreign_origin(live: str) -> None:
    request = urllib.request.Request(
        f"{live}/api/jarvis/health", headers={"Origin": "http://evil.example"}
    )
    with urllib.request.urlopen(request, timeout=5) as response:
        assert response.headers.get("Access-Control-Allow-Origin") is None


def test_broken_json_body_is_400(live: str) -> None:
    request = urllib.request.Request(
        f"{live}/api/jarvis/ask",
        data=b"{not json",
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    with pytest.raises(urllib.error.HTTPError) as error:
        urllib.request.urlopen(request, timeout=5)
    assert error.value.code == 400


def test_sse_encoding_is_one_json_line() -> None:
    encoded = encode_event({"type": "scene", "scene_id": "s-01"})
    assert encoded.startswith(b"data: ")
    assert encoded.endswith(b"\n\n")
    assert encoded.count(b"\n") == 2


def test_chunk_frames_the_payload() -> None:
    framed = chunk(b"abc")
    assert framed == b"3\r\nabc\r\n"


def test_error_event_carries_a_code() -> None:
    payload = json.loads(
        error_event("timeout", "took too long").decode("utf-8")[len("data: ") :]
    )
    assert payload == {
        "type": "error",
        "code": "timeout",
        "message": "took too long",
    }


def test_error_event_can_be_joined_to_request() -> None:
    payload = json.loads(
        error_event("timeout", "took too long", "req-1", 504).decode("utf-8")[len("data: ") :]
    )
    assert payload["request_id"] == "req-1"
    assert payload["http_status"] == 504


class SlowFakeClient(FakeChatClient):
    def stream(self, messages: Any, tools: Any, system: str, cancellation: Any = None) -> Any:
        time.sleep(0.3)
        yield from super().stream(messages, tools, system, cancellation)


@pytest.fixture()
def slow(store: ArtifactStore, knowledge: Knowledge) -> Iterator[str]:
    client = SlowFakeClient(rounds=[[CALL]], caption=CAPTION, model="fake/slow")
    orchestrator = Orchestrator(
        client=client, store=store, knowledge=knowledge, sessions=SessionStore()
    )
    service = JarvisService(
        store=store, knowledge=knowledge, env={}, orchestrator=orchestrator
    )
    yield from run(service)


def test_keepalive_comment_fills_a_silent_gap(
    slow: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sse, "KEEPALIVE_SECONDS", 0.05)
    response = post(
        f"{slow}/api/jarvis/ask",
        {"session_id": "s-keepalive", "question": "что с фондом"},
    )
    lines = [raw.decode("utf-8").rstrip("\r\n") for raw in response]
    assert any(line.startswith(":") for line in lines)
    assert any(line.startswith("data:") for line in lines)


def test_keepalive_writer_pulses_only_when_idle() -> None:
    sink = io.BytesIO()
    writer = sse.KeepAliveWriter(sink, interval=0.06)
    with writer:
        writer.write(b"data: {}\n\n")
        time.sleep(0.25)
    body = sink.getvalue()
    assert b"data: {}" in body
    assert sse.KEEPALIVE_COMMENT in body
    assert writer.failure is None


def test_keepalive_writer_stays_quiet_while_events_flow() -> None:
    sink = io.BytesIO()
    writer = sse.KeepAliveWriter(sink, interval=5.0)
    with writer:
        writer.write(b"data: {}\n\n")
        time.sleep(0.1)
    assert sse.KEEPALIVE_COMMENT not in sink.getvalue()


def test_keepalive_writer_reports_a_disconnected_client() -> None:
    class BrokenSink:
        def write(self, body: bytes) -> int:
            raise BrokenPipeError("client disconnected")

        def flush(self) -> None:
            return None

    failures: list[str] = []
    writer = sse.KeepAliveWriter(
        BrokenSink(),
        interval=0.03,
        on_failure=lambda: failures.append("cancelled"),
    )
    with writer:
        time.sleep(0.07)

    assert isinstance(writer.failure, BrokenPipeError)
    assert failures == ["cancelled"]

@pytest.mark.parametrize("code", ["provider-timeout", UpstreamError.default_code])
def test_recorded_journal_fallback_reports_provider_failure_in_health(store, knowledge, monkeypatch, code):
    from backend.contexts.assistant.application.tools.context import Card
    payload = json.loads((repo_root() / "tests/backend/contexts/assistant/fixtures/journal_s10.json").read_text())
    card = Card(type="rule", title="Журнал", payload=payload, provenance="recorded-generation-journal")
    monkeypatch.setattr("backend.contexts.assistant.application.orchestrator_compose.run_tool", lambda *args: card)
    class FailedClient(FakeChatClient):
        def stream(self, *args, **kwargs):
            raise UpstreamError("provider unavailable", code=code)
            yield
    orchestrator = Orchestrator(client=FailedClient(rounds=[], caption=""), store=store, knowledge=knowledge)
    service = JarvisService(store=store, knowledge=knowledge, env={}, orchestrator=orchestrator)
    with contextmanager(run)(service) as url:
        events = read_events(post(f"{url}/api/jarvis/ask", {
            "session_id": "fallback-health", "question": "Раскрой журнал решений этой скважины",
            "context": {"run_id": payload["run_id"], "selected_well": "62", "step": 0},
        }))
        assert next(event for event in events if event["type"] == "done")["provider_error_code"] == code
        with urllib.request.urlopen(f"{url}/api/jarvis/health", timeout=5) as response:
            health = json.loads(response.read())
        assert health["last_request"]["outcome"] == "fallback"
        assert health["last_request"]["error_code"] == code


def test_http_overflow_finishes_without_auxiliary_summary_llm(store, knowledge, tmp_path):
    from backend.contexts.assistant.domain.session import HISTORY_LIMIT
    class SlowSummaryClient(FakeChatClient):
        summary_calls = 0
        def stream(self, messages, *args, **kwargs):
            if any("Сожми эти обмены" in str(message.content) for message in messages):
                self.summary_calls += 1
                time.sleep(0.15)
            yield from super().stream(messages, *args, **kwargs)
    disk = SessionDisk(tmp_path / "sessions")
    for index in range(HISTORY_LIMIT):
        disk.append("memory-http", {"type": "ask", "question": f"Archived question {index}"})
        disk.append("memory-http", {"type": "caption", "text": "Archived observed35"})
    client = SlowSummaryClient(rounds=[], caption="Ready answer.")
    orchestrator = Orchestrator(client=client, store=store, knowledge=knowledge, disk=disk)
    service = JarvisService(store=store, knowledge=knowledge, env={}, orchestrator=orchestrator)
    with contextmanager(run)(service) as url:
        started = time.monotonic()
        events = read_events(post(f"{url}/api/jarvis/ask", {"session_id": "memory-http", "question": "New question"}))
        elapsed = time.monotonic() - started
        assert events[-1]["type"] == "done"
        assert client.summary_calls == 0
        assert elapsed < 0.12
        assert "Archived observed35" in SessionStore(disk=SessionDisk(tmp_path / "sessions")).get("memory-http").summary_text
