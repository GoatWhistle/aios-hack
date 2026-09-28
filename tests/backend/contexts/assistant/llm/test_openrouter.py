from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Iterator

import pytest

from backend.contexts.assistant.domain.cancellation import CancellationToken
from backend.contexts.assistant.infrastructure.llm.chat_events import (
    ChatMessage,
    Done,
    TextDelta,
    ToolCall,
    ToolSpec,
)
from backend.contexts.assistant.infrastructure.llm.openrouter import (
    OpenRouterClient,
    UpstreamError,
    parse_sse_lines,
)

TOOL = ToolSpec(
    name="well_snapshot",
    description="снимок скважины",
    schema={
        "type": "object",
        "properties": {"well": {"type": "string"}, "step": {"type": "integer"}},
        "required": ["well"],
    },
)

RECORDED_TOOL_STREAM: tuple[str, ...] = (
    ': OPENROUTER PROCESSING',
    'data: {"id":"gen-1","choices":[{"index":0,"delta":{"role":"assistant","content":""}}]}',
    'data: {"id":"gen-1","choices":[{"index":0,"delta":{"tool_calls":[{"index":0,"id":"call_a","type":"function","function":{"name":"well_snapshot","arguments":""}}]}}]}',
    'data: {"id":"gen-1","choices":[{"index":0,"delta":{"tool_calls":[{"index":0,"function":{"arguments":"{\\"we"}}]}}]}',
    'data: {"id":"gen-1","choices":[{"index":0,"delta":{"tool_calls":[{"index":0,"function":{"arguments":"ll\\": \\"13"}}]}}]}',
    'data: {"id":"gen-1","choices":[{"index":0,"delta":{"tool_calls":[{"index":0,"function":{"arguments":"\\", \\"step\\": 96}"}}]}}]}',
    'data: {"id":"gen-1","choices":[{"index":0,"delta":{"tool_calls":[{"index":1,"id":"call_b","type":"function","function":{"name":"field_metrics","arguments":"{\\"step\\":"}}]}}]}',
    'data: {"id":"gen-1","choices":[{"index":0,"delta":{"tool_calls":[{"index":1,"function":{"arguments":" 96}"}}]}}]}',
    'data: {"id":"gen-1","choices":[{"index":0,"delta":{},"finish_reason":"tool_calls"}],"usage":{"prompt_tokens":11,"completion_tokens":7}}',
    "data: [DONE]",
)

RECORDED_TEXT_STREAM: tuple[str, ...] = (
    'data: {"id":"gen-2","choices":[{"index":0,"delta":{"content":"Скважина 13 "}}]}',
    'data: {"id":"gen-2","choices":[{"index":0,"delta":{"content":"работает."}}]}',
    'data: {"id":"gen-2","choices":[{"index":0,"delta":{},"finish_reason":"stop"}]}',
    "data: [DONE]",
)


class _Recorder:
    def __init__(self) -> None:
        self.lines: list[str] = []
        self.status: int = 200
        self.bodies: list[dict[str, Any]] = []
        self.authorization: str | None = None


def _handler(recorder: _Recorder) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *args: Any) -> None:
            return

        def do_POST(self) -> None:
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length)
            recorder.bodies.append(json.loads(raw.decode("utf-8")))
            recorder.authorization = self.headers.get("Authorization")
            if recorder.status != 200:
                payload = json.dumps({"error": {"message": "перегрузка"}}).encode()
                self.send_response(recorder.status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
                return
            body = ("\n\n".join(recorder.lines) + "\n\n").encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    return Handler


@pytest.fixture()
def server() -> Iterator[tuple[str, _Recorder]]:
    recorder = _Recorder()
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), _handler(recorder))
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    host, port = httpd.server_address[0], httpd.server_address[1]
    try:
        yield f"http://{host}:{port}", recorder
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=5)


def test_split_tool_arguments_are_reassembled(
    server: tuple[str, _Recorder],
) -> None:
    base_url, recorder = server
    recorder.lines = list(RECORDED_TOOL_STREAM)
    client = OpenRouterClient(api_key="k", base_url=base_url, model="test/model")
    events = list(
        client.stream([ChatMessage(role="user", content="что со скважиной 13")], [TOOL], "система")
    )
    calls = [event for event in events if isinstance(event, ToolCall)]
    assert [call.name for call in calls] == ["well_snapshot", "field_metrics"]
    assert calls[0].args == {"well": "13", "step": 96}
    assert calls[0].id == "call_a"
    assert calls[1].args == {"step": 96}
    done = events[-1]
    assert isinstance(done, Done)
    assert done.stop == "tool_calls"
    assert done.usage == {"prompt_tokens": 11, "completion_tokens": 7}


def test_text_stream_yields_deltas(server: tuple[str, _Recorder]) -> None:
    base_url, recorder = server
    recorder.lines = list(RECORDED_TEXT_STREAM)
    client = OpenRouterClient(api_key="k", base_url=base_url)
    events = list(client.stream([ChatMessage(role="user", content="?")], [], "система"))
    deltas = [event.text for event in events if isinstance(event, TextDelta)]
    assert deltas == ["Скважина 13 ", "работает."]
    assert isinstance(events[-1], Done)
    assert events[-1].stop == "stop"


def test_request_body_carries_tools_and_stream(server: tuple[str, _Recorder]) -> None:
    base_url, recorder = server
    recorder.lines = list(RECORDED_TEXT_STREAM)
    client = OpenRouterClient(api_key="secret", base_url=base_url, model="m/x")
    list(client.stream([ChatMessage(role="user", content="?")], [TOOL], "система"))
    body = recorder.bodies[-1]
    assert body["stream"] is True
    assert body["model"] == "m/x"
    assert body["messages"][0] == {"role": "system", "content": "система"}
    assert body["tools"][0]["function"]["name"] == "well_snapshot"
    assert body["tools"][0]["function"]["parameters"]["required"] == ["well"]
    assert recorder.authorization == "Bearer secret"


def test_retry_once_then_report_upstream(server: tuple[str, _Recorder]) -> None:
    base_url, recorder = server
    recorder.status = 429
    recorder.lines = list(RECORDED_TEXT_STREAM)
    client = OpenRouterClient(api_key="k", base_url=base_url)
    with pytest.raises(UpstreamError) as error:
        list(client.stream([ChatMessage(role="user", content="?")], [], "s"))
    assert "429" in str(error.value)
    assert error.value.code == "provider-rate-limit"
    assert error.value.details["http_status"] == 429
    assert len(recorder.bodies) == 2


@pytest.mark.parametrize(
    ("status", "expected_code", "expected_attempts"),
    [(401, "provider-auth", 1), (503, "provider-server-error", 2)],
)
def test_http_provider_failures_keep_actionable_category(
    server: tuple[str, _Recorder],
    status: int,
    expected_code: str,
    expected_attempts: int,
) -> None:
    base_url, recorder = server
    recorder.status = status
    client = OpenRouterClient(api_key="k", base_url=base_url)

    with pytest.raises(UpstreamError) as error:
        list(client.stream([ChatMessage(role="user", content="?")], [], "s"))

    assert error.value.code == expected_code
    assert error.value.details["http_status"] == status
    assert len(recorder.bodies) == expected_attempts


def test_cancellation_closes_a_blocked_provider_stream() -> None:
    headers_sent = threading.Event()
    allow_server_exit = threading.Event()

    class HangingHandler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *args: Any) -> None:
            return

        def do_POST(self) -> None:
            length = int(self.headers.get("Content-Length", "0"))
            self.rfile.read(length)
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Transfer-Encoding", "chunked")
            self.end_headers()
            self.wfile.write(b"A\r\n: waiting\n\r\n")
            self.wfile.flush()
            headers_sent.set()
            allow_server_exit.wait(3)

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), HangingHandler)
    httpd.daemon_threads = True
    server_thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    server_thread.start()
    token = CancellationToken()
    client = OpenRouterClient(
        api_key="k",
        base_url=f"http://127.0.0.1:{httpd.server_address[1]}",
        timeout=5,
    )
    failures: list[BaseException] = []

    def read_stream() -> None:
        try:
            list(client.stream([ChatMessage(role="user", content="?")], [], "s", token))
        except BaseException as error:
            failures.append(error)

    reader = threading.Thread(target=read_stream, daemon=True)
    try:
        reader.start()
        assert headers_sent.wait(2)
        token.cancel()
        reader.join(timeout=1.5)
        assert not reader.is_alive(), "cancel must unblock the provider stream read"
        assert len(failures) == 1
        assert isinstance(failures[0], UpstreamError)
        assert failures[0].code == "cancelled"
    finally:
        allow_server_exit.set()
        httpd.shutdown()
        httpd.server_close()
        server_thread.join(timeout=2)


def test_total_stream_timeout_includes_silent_sse_wait() -> None:
    headers_sent = threading.Event()
    allow_server_exit = threading.Event()

    class SilentHandler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *args: Any) -> None:
            return

        def do_POST(self) -> None:
            length = int(self.headers.get("Content-Length", "0"))
            self.rfile.read(length)
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Transfer-Encoding", "chunked")
            self.end_headers()
            self.wfile.flush()
            headers_sent.set()
            allow_server_exit.wait(2)
            try:
                self.wfile.write(b"A\r\ndata: [DONE]\n\r\n")
                self.wfile.flush()
            except OSError:
                pass

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), SilentHandler)
    httpd.daemon_threads = True
    server_thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    server_thread.start()
    client = OpenRouterClient(
        api_key="k",
        base_url=f"http://127.0.0.1:{httpd.server_address[1]}",
        timeout=0.2,
    )
    started = time.monotonic()
    try:
        with pytest.raises(UpstreamError) as error:
            list(client.stream([ChatMessage(role="user", content="?")], [], "s"))
        elapsed = time.monotonic() - started
        assert headers_sent.is_set()
        assert error.value.code == "provider-timeout"
        assert elapsed < 1.0
    finally:
        allow_server_exit.set()
        httpd.shutdown()
        httpd.server_close()
        server_thread.join(timeout=2)


def test_total_stream_timeout_includes_trickling_partial_sse_line() -> None:
    stop = threading.Event()

    class TrickleHandler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *args: Any) -> None:
            return

        def do_POST(self) -> None:
            self.rfile.read(int(self.headers.get("Content-Length", "0")))
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Transfer-Encoding", "chunked")
            self.end_headers()
            try:
                tool_frame = json.dumps({"choices": [{"delta": {"tool_calls": [{
                    "index": 0, "id": "partial-tool", "function": {"name": "well_snapshot", "arguments": '{"well":"62"}'}
                }]}}]})
                frame = f"data: {tool_frame}\n\n".encode()
                self.wfile.write(f"{len(frame):X}\r\n".encode() + frame + b"\r\n")
                # Each byte resets the socket inactivity timeout, but no
                # complete SSE line exists until well past the total budget.
                for _ in range(60):
                    self.wfile.write(b"1\r\n \r\n")
                    self.wfile.flush()
                    if stop.wait(0.01):
                        return
                self.wfile.write(b"2\r\n\n\n\r\n0\r\n\r\n")
                self.wfile.flush()
            except OSError:
                pass

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), TrickleHandler)
    httpd.daemon_threads = True
    server = threading.Thread(target=httpd.serve_forever, daemon=True)
    server.start()
    client = OpenRouterClient(api_key="local-test", base_url=f"http://127.0.0.1:{httpd.server_address[1]}", timeout=0.1)
    started = time.monotonic()
    events = []
    try:
        with pytest.raises(UpstreamError) as error:
            for event in client.stream([ChatMessage(role="user", content="?")], [], "s"):
                events.append(event)
        assert error.value.code == "provider-timeout"
        assert time.monotonic() - started < 0.4
        assert not any(isinstance(event, ToolCall) for event in events)
    finally:
        stop.set()
        httpd.shutdown()
        httpd.server_close()
        server.join(timeout=2)


def test_broken_json_arguments_reported(server: tuple[str, _Recorder]) -> None:
    base_url, recorder = server
    recorder.lines = [
        'data: {"choices":[{"index":0,"delta":{"tool_calls":[{"index":0,"id":"c","type":"function","function":{"name":"well_snapshot","arguments":"{\\"well\\":"}}]}}]}',
        'data: {"choices":[{"index":0,"delta":{},"finish_reason":"tool_calls"}]}',
        "data: [DONE]",
    ]
    client = OpenRouterClient(api_key="k", base_url=base_url)
    with pytest.raises(UpstreamError) as error:
        list(client.stream([ChatMessage(role="user", content="?")], [TOOL], "s"))
    assert "incomplete JSON" in str(error.value)


def test_sse_parser_skips_comments_and_stops_on_done() -> None:
    lines = iter([": keep-alive", "", 'data: {"a": 1}', "data: [DONE]", 'data: {"b": 2}'])
    assert list(parse_sse_lines(lines)) == [{"a": 1}]


def test_sse_parser_rejects_broken_line() -> None:
    with pytest.raises(UpstreamError):
        list(parse_sse_lines(iter(["data: {не json}"])))


def test_missing_key_refuses() -> None:
    with pytest.raises(RuntimeError) as error:
        OpenRouterClient(api_key="")
    assert "OPENROUTER_API_KEY" in str(error.value)
