from __future__ import annotations

import json
import threading
import time
from types import SimpleNamespace
from pathlib import Path

import pytest

from backend.contexts.assistant.infrastructure.artifacts import ArtifactStore
from backend.contexts.assistant.application.recording_replay import replay, to_jsonl
from backend.contexts.assistant.infrastructure.knowledge import Knowledge
from backend.contexts.assistant.application.orchestrator import Orchestrator
from backend.contexts.assistant.application.orchestrator import _contextual_tool_preset
from backend.contexts.assistant.infrastructure.recordings import RECORDINGS
from backend.contexts.assistant.infrastructure.prompt import prompt_resources
from backend.contexts.assistant.domain.session import Exchange, SessionError, SessionStore
from backend.contexts.assistant.application.tools.context import ConsoleContext
from backend.contexts.assistant.application.tools import HANDLERS
from backend.contexts.assistant.infrastructure.llm.chat_events import ToolCall
from backend.contexts.assistant.infrastructure.llm.fake_chat import FakeChatClient

EVENT_ORDER = (
    "scene",
    "capabilities",
    "status",
    "card",
    "caption_delta",
    "caption",
    "answer_delta",
    "answer",
    "suggestions",
    "done",
)


def test_e2e_conclusion_answer_preserves_sources_and_corrects_download_claim(
    store: ArtifactStore, knowledge: Knowledge, monkeypatch: pytest.MonkeyPatch
) -> None:
    from backend.contexts.assistant.application.tools.context import Card

    run_id = "jarvis-policy-20260926"
    url = f"/api/jarvis/run-artifacts/{run_id}/manifest"
    payload = {"run_id": run_id, "conclusion_markdown": f"# Заключение\n[manifest]({url})", "has_submission": False}
    card = Card(type="run", title="Прогон", payload=payload, provenance="runs")
    monkeypatch.setattr("backend.contexts.assistant.application.orchestrator.call_tool", lambda *args: (card, payload))
    client = FakeChatClient(
        rounds=[[ToolCall(id="c", name="run_detail", args={"run_id": run_id})]],
        caption=(f"Пакет сдачи не собран, отдельного файла для скачивания нет.\n---ОТВЕТ---\n"
                 f"- **Прогон:** `{run_id}`\n- [Манифест]( {url} )\n"
                 "Пакет сдачи отсутствует, поэтому единого файла для скачивания нет."),
    )
    events = list(Orchestrator(client=client, store=store, knowledge=knowledge).ask(
        "conclusion-e2e", "Покажи инженерное заключение", ConsoleContext(run_id=run_id)
    ))
    caption = next(event.body["text"] for event in events if event.type == "caption")
    answer = next(event.body["text"] for event in events if event.type == "answer")
    assert run_id in answer and url in answer
    assert "можно скачать на карточке" in caption
    assert "можно скачать на карточке" in answer
    assert "файла для скачивания нет" not in caption + answer
    assert any(event.body.get("code") == "delivery-claim-conflict" for event in events if event.type == "warning")


def test_ask_after_restarting_legacy_session_keeps_replay_scene_ids_unique(
    store: ArtifactStore, knowledge: Knowledge, tmp_path: Path
) -> None:
    from backend.contexts.assistant.infrastructure.session_store import SessionDisk

    root = tmp_path / "sessions"
    disk = SessionDisk(root)
    for question in ("Первый вопрос", "Второй вопрос"):
        disk.append("legacy", {"type": "ask", "question": question})
        disk.append("legacy", {"type": "scene", "scene_id": "s-05", "question": question})
        disk.append("legacy", {"type": "caption", "scene_id": "s-05", "text": question})
    prefix = disk.events("legacy")
    for expected in ("s-07", "s-08"):
        archive = SessionDisk(root)
        orchestrator = Orchestrator(
            client=FakeChatClient(rounds=[], caption="Текущий ответ."),
            store=store, knowledge=knowledge, disk=archive,
        )
        events = list(orchestrator.ask("legacy", "Продолжи диалог", ConsoleContext()))
        assert next(event.body["scene_id"] for event in events if event.type == "scene") == expected
        replayed = archive.events("legacy")
        assert replayed[:len(prefix)] == prefix
        identities = [event["scene_id"] for event in replayed if event["type"] == "scene"]
        assert len(identities) == len(set(identities))


def test_journal_answer_retains_recorded_facts_without_empty_numeric_holes(
    store: ArtifactStore, knowledge: Knowledge, monkeypatch: pytest.MonkeyPatch
) -> None:
    from backend.contexts.assistant.application.tools.context import Card

    payload = json.loads((Path(__file__).parent / "fixtures/journal_s10.json").read_text())
    card = Card(type="rule", title="Журнал решения", payload=payload, provenance="recorded-decision")
    monkeypatch.setattr("backend.contexts.assistant.application.orchestrator.call_tool", lambda *args: (card, payload))
    model_answer = (
        "Изменение записано в журнале.\n---ОТВЕТ---\n"
        "### Что записано в журнале\n\n"
        "- **Скважина:** 62, нагнетательная, открыта.\n"
        "- **Исходная уставка и закачка:** 35 м³/сут.\n"
        "- **R1:** целевой уровень 0 м³/сут при лимите 69.76533612172533 м³/сут.\n"
        "- **R5:** целевой уровень 2.043192584753177 м³/сут при компенсации 1.3719989114061593 и коридоре 0.9–1.15.\n"
        "- **Итоговое событие расписания:** `SET_RATE` со значением `1`, затем `OPEN`.\n"
        "План лучший, выигрыш 999999 рублей."
    )
    client = FakeChatClient(rounds=[[ToolCall(id="j", name="decision_journal", args={"run_id": payload['run_id'], "well": "62", "control_step": 0})]], caption=model_answer)
    events = list(Orchestrator(client=client, store=store, knowledge=knowledge).ask(
        "journal-integrity", "Почему изменили уставку?", ConsoleContext(run_id=payload['run_id'], selected_well="62", step=0)
    ))
    answer = next(event.body["text"] for event in events if event.type == "answer")
    assert "Скважина 62" in answer
    assert "35 м³/сут" in answer
    assert "2.043" in answer
    assert "0.9" in answer and "1.15" in answer
    assert "SET_RATE" in answer and "1 м³/сут" in answer
    assert "не записан" in answer.casefold()
    assert "999999" not in answer and "лучший" not in answer
    assert "**Скважина:**," not in answer
    assert "**Исходная уставка и закачка:** м³/сут" not in answer


def test_run_chart_metadata_reaches_model_without_time_series_measurements(
    store: ArtifactStore, knowledge: Knowledge, monkeypatch: pytest.MonkeyPatch
) -> None:
    from backend.contexts.assistant.application.tools.context import Card

    payload = json.loads((Path(__file__).parent / "fixtures/journal_s10.json").read_text())
    payload["run_series"] = {
        "metric": "injection_rate", "unit": "m3/day", "input_source": "input_observation",
        "schedule_source": "final_schedule_events", "rows": [
            {"step": 0, "date": "2007-01-01", "input_rate": 35.0, "scheduled_rate": 1.0},
            {"step": 1, "date": "2007-02-01", "input_rate": 987654321.0, "scheduled_rate": 0.0},
        ],
    }
    card = Card(type="rule", title="Журнал", payload=payload, provenance="recorded-generation-journal")
    monkeypatch.setattr("backend.contexts.assistant.application.orchestrator_compose.run_tool", lambda *args: card)
    client = FakeChatClient(rounds=[[ToolCall(id="j", name="decision_journal", args={"run_id": payload["run_id"], "well": "62", "control_step": 0})]], caption="График доступен на карточке.")
    list(Orchestrator(client=client, store=store, knowledge=knowledge).ask(
        "chart-model-context", "Покажи журнал", ConsoleContext(run_id=payload["run_id"], selected_well="62", step=0)
    ))
    model_results = [json.loads(message.content) for messages, _ in client.calls for message in messages if message.role == "tool"]
    assert model_results
    info = model_results[0]["run_series_info"]
    assert info == {
        "available": True, "has_multiple_steps": True, "metric": "injection_rate", "unit": "m3/day",
        "input_source": "input_observation", "schedule_source": "final_schedule_events",
        "from_date": "2007-01-01", "to_date": "2007-02-01",
    }
    assert "run_series" not in model_results[0]
    assert "987654321" not in json.dumps(model_results[0])


def test_caption_cannot_deny_the_recorded_run_chart(
    store: ArtifactStore, knowledge: Knowledge, monkeypatch: pytest.MonkeyPatch
) -> None:
    from backend.contexts.assistant.application.tools.context import Card

    payload = json.loads((Path(__file__).parent / "fixtures/journal_s10.json").read_text())
    payload["run_series"] = {"metric": "injection_rate", "unit": "m3/day", "rows": [
        {"step": 0, "date": "2007-01-01", "input_rate": 35.0, "scheduled_rate": 1.0},
        {"step": 1, "date": "2007-02-01", "input_rate": 35.0, "scheduled_rate": 0.0},
    ]}
    card = Card(type="rule", title="Журнал", payload=payload, provenance="recorded-generation-journal")
    monkeypatch.setattr("backend.contexts.assistant.application.orchestrator_compose.run_tool", lambda *args: card)
    client = FakeChatClient(
        rounds=[[ToolCall(id="j", name="decision_journal", args={"run_id": payload["run_id"], "well": "62", "control_step": 0})]],
        caption="Записана только точка шага 0, временной ряд не записан отдельно.\n---ОТВЕТ---\nГрафик отсутствует.",
    )
    events = list(Orchestrator(client=client, store=store, knowledge=knowledge).ask(
        "chart-denial", "Покажи журнал", ConsoleContext(run_id=payload["run_id"], selected_well="62", step=0)
    ))
    caption = next(event.body["text"] for event in events if event.type == "caption")
    answer = next(event.body["text"] for event in events if event.type == "answer")
    assert "График прогона показан на карточке" in caption
    assert "График прогона показан на карточке" in answer
    assert "только точка" not in caption and "не записан" not in caption
    assert "График отсутствует" not in answer


def test_provider_timeout_after_one_journal_finishes_with_honest_recorded_facts(
    store: ArtifactStore, knowledge: Knowledge, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from backend.contexts.assistant.domain.errors import UpstreamError
    from backend.contexts.assistant.infrastructure.session_store import SessionDisk
    from backend.contexts.assistant.application.tools.context import Card

    payload = json.loads((Path(__file__).parent / "fixtures/journal_s10.json").read_text())
    card = Card(type="rule", title="Журнал", payload=payload, provenance="recorded-generation-journal")
    monkeypatch.setattr("backend.contexts.assistant.application.orchestrator_compose.run_tool", lambda *args: card)
    elapsed = {"value": 0.0}

    class TimingOutClient(FakeChatClient):
        def stream(self, *args, **kwargs):
            if self.turns:
                elapsed["value"] = 120.0
                raise UpstreamError("provider exceeded budget", code="provider-timeout")
            yield from super().stream(*args, **kwargs)

    client = TimingOutClient(rounds=[[ToolCall(id="j", name="decision_journal", args={"run_id": payload["run_id"], "well": "62", "control_step": 0})]], caption="")
    disk = SessionDisk(tmp_path / "sessions")
    orchestrator = Orchestrator(client=client, store=store, knowledge=knowledge, disk=disk, clock=lambda: elapsed["value"])
    events = list(orchestrator.ask("timeout-journal", "Покажи журнал", ConsoleContext(run_id=payload["run_id"], selected_well="62", step=0)))
    caption = next(event for event in events if event.type == "caption")
    answer = next(event for event in events if event.type == "answer")
    done = next(event for event in events if event.type == "done")
    assert "Модель не ответила вовремя" in caption.body["text"]
    assert "35 м³/сут" in answer.body["text"] and "`SET_RATE` 1 м³/сут" in answer.body["text"]
    assert answer.body["provenance"] == "recorded-generation-journal"
    assert done.body["completion"] == "recorded-journal-fallback"
    assert any(event.type == "warning" and event.body["code"] == "provider-timeout" for event in events)
    assert orchestrator.sessions.get("timeout-journal").history[-1].answer == answer.body["text"]
    assert any(event["type"] == "done" for event in disk.events("timeout-journal"))


def test_timeout_reply_requires_one_journal_but_allows_companion_cards() -> None:
    from backend.contexts.assistant.application.orchestrator_compose import provider_failure_journal_reply
    from backend.contexts.assistant.application.tools.context import Card

    payload = json.loads((Path(__file__).parent / "fixtures/journal_s10.json").read_text())
    journal = Card(type="rule", title="Журнал", payload=payload, provenance="recorded-generation-journal")
    companion = Card(type="connectivity", title="Связи", payload={}, provenance="showcase")
    other_payload = dict(payload, well="42")
    other_journal = Card(type="rule", title="Другой журнал", payload=other_payload, provenance="recorded-generation-journal")
    assert provider_failure_journal_reply([], "ru") is None
    assert provider_failure_journal_reply([companion], "ru") is None
    assert provider_failure_journal_reply([journal, companion], "ru") is not None
    assert provider_failure_journal_reply([journal, other_journal], "ru") is None


@pytest.mark.parametrize("code", ["cancelled", "internal"])
def test_cancelled_or_internal_failure_does_not_generate_recorded_fallback(
    store: ArtifactStore, knowledge: Knowledge, monkeypatch: pytest.MonkeyPatch, code: str
) -> None:
    from backend.contexts.assistant.domain.errors import UpstreamError
    from backend.contexts.assistant.application.tools.context import Card

    payload = json.loads((Path(__file__).parent / "fixtures/journal_s10.json").read_text())
    card = Card(type="rule", title="Журнал", payload=payload, provenance="recorded-generation-journal")
    monkeypatch.setattr("backend.contexts.assistant.application.orchestrator_compose.run_tool", lambda *args: card)

    class FailingClient(FakeChatClient):
        def stream(self, *args, **kwargs):
            if self.turns:
                if code == "internal":
                    raise RuntimeError("internal failure")
                raise UpstreamError("provider failed", code=code)
            yield from super().stream(*args, **kwargs)

    client = FailingClient(rounds=[[ToolCall(id="j", name="decision_journal", args={"run_id": payload["run_id"], "well": "62", "control_step": 0})]], caption="")
    events = []
    with pytest.raises(RuntimeError if code == "internal" else UpstreamError) as error:
        for event in Orchestrator(client=client, store=store, knowledge=knowledge).ask(
            "non-timeout", "Покажи журнал", ConsoleContext(run_id=payload["run_id"], selected_well="62", step=0)
        ):
            events.append(event)
    if code != "internal":
        assert error.value.code == code
    assert not any(event.type in {"caption", "answer", "done"} for event in events)


def test_default_typed_upstream_failure_after_journal_keeps_factual_reply(
    store: ArtifactStore, knowledge: Knowledge, monkeypatch: pytest.MonkeyPatch
) -> None:
    from backend.contexts.assistant.domain.errors import UpstreamError
    from backend.contexts.assistant.application.tools.context import Card

    payload = json.loads((Path(__file__).parent / "fixtures/journal_s10.json").read_text())
    card = Card(type="rule", title="Журнал", payload=payload, provenance="recorded-generation-journal")
    monkeypatch.setattr("backend.contexts.assistant.application.orchestrator_compose.run_tool", lambda *args: card)

    class UnavailableClient(FakeChatClient):
        def stream(self, *args, **kwargs):
            if self.turns:
                raise UpstreamError("provider unavailable")
            yield from super().stream(*args, **kwargs)

    client = UnavailableClient(rounds=[[ToolCall(id="j", name="decision_journal", args={"run_id": payload["run_id"], "well": "62", "control_step": 0})]], caption="")
    events = list(Orchestrator(client=client, store=store, knowledge=knowledge).ask(
        "unavailable-journal", "Покажи журнал", ConsoleContext(run_id=payload["run_id"], selected_well="62", step=0)
    ))
    caption = next(event.body for event in events if event.type == "caption")
    answer = next(event.body for event in events if event.type == "answer")
    done = next(event.body for event in events if event.type == "done")
    assert "Модель недоступна" in caption["text"]
    assert "35 м³/сут" in answer["text"]
    assert answer["provenance"] == "recorded-generation-journal"
    assert done["completion"] == "recorded-journal-fallback" and done["provider_status"] == "error"
    assert any(event.type == "warning" and event.body["code"] == UpstreamError.default_code for event in events)


def test_unretrieved_run_documents_do_not_authorize_answer_numbers(
    store: ArtifactStore, knowledge: Knowledge,
) -> None:
    record = SimpleNamespace(documents=lambda: ({"unrelated_measurement": 987654321},))
    runs = SimpleNamespace(read=lambda *args: record)
    client = FakeChatClient(rounds=[], caption="Recorded value is 987654321.")
    orchestrator = Orchestrator(client=client, store=store, knowledge=knowledge, runs=runs)
    events = list(orchestrator.ask("evidence-boundary", "Show recorded values", ConsoleContext()))
    captions = [event.body["text"] for event in events if event.type == "caption"]
    assert captions
    assert all("987654321" not in text for text in captions)


def test_ambient_evidence_uses_only_explicit_run(store: ArtifactStore) -> None:
    from backend.contexts.assistant.application.orchestrator_compose import evidence_of
    from backend.contexts.assistant.application.tools.context import ToolContext

    reads = []
    def read(run_id=None):
        reads.append(run_id)
        return SimpleNamespace(documents=lambda: ({"run_id": run_id},))

    runs = SimpleNamespace(read=read)
    context = ToolContext(store=store, runs=runs, console=ConsoleContext(run_id="selected-run"))
    assert evidence_of(context) == ({"run_id": "selected-run"},)
    assert evidence_of(ToolContext(store=store, runs=runs)) == ()
    assert reads == ["selected-run"]


@pytest.mark.parametrize(
    ("lang", "required_phrases"),
    [
        ("ru", ("точную причину из message", "предложи next_step", "не утверждай")),
        ("en", ("exact reason from message", "suggest next_step", "Do not claim")),
    ],
)
def test_prompt_requires_tool_failure_reason_and_next_step(
    lang: str, required_phrases: tuple[str, ...]
) -> None:
    rules = " ".join(prompt_resources(lang).lines("rules"))

    for phrase in required_phrases:
        assert phrase.casefold() in rules.casefold()


@pytest.mark.parametrize("lang, phrase", [
    ("ru", "Явный запрос графика или временного ряда обязательно проверяй через well_series"),
    ("en", "An explicit request for a chart or time series must use well_series"),
])
def test_prompt_requires_time_series_tool_for_explicit_chart_request(lang: str, phrase: str) -> None:
    playbook = " ".join(prompt_resources(lang).lines("playbook"))
    assert phrase.casefold() in playbook.casefold()


@pytest.mark.parametrize(
    ("lang", "required_phrases"),
    [
        ("ru", ("формулу из карточки дословно", "не оставляй пустой заголовок", "не восстанавливай её по памяти")),
        ("en", ("reproduce the formula from the card exactly", "never leave a blank formula heading", "do not reconstruct it from memory")),
    ],
)
def test_prompt_preserves_only_retrieved_formulas(
    lang: str, required_phrases: tuple[str, ...]
) -> None:
    playbook = " ".join(prompt_resources(lang).lines("playbook"))
    for phrase in required_phrases:
        assert phrase.casefold() in playbook.casefold()


@pytest.fixture(scope="module")
def knowledge() -> Knowledge:
    return Knowledge()


@pytest.mark.parametrize("recording", RECORDINGS, ids=lambda r: r.name)
def test_fixture_replays_with_stable_events(
    recording, store: ArtifactStore, knowledge: Knowledge, fixtures_root: Path
) -> None:
    produced = [
        json.loads(line)
        for line in to_jsonl(replay(recording, store, knowledge)).splitlines()
    ]
    stored = [
        json.loads(line)
        for line in (fixtures_root / f"{recording.name}.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    assert _stable_replay(produced) == _stable_replay(stored)


def _stable_replay(events: list[dict]) -> list[dict]:
    """Keep replay checks stable across corpus and instrumentation changes."""
    normalized = json.loads(json.dumps(events, ensure_ascii=False))
    for event in normalized:
        if event.get("type") == "done":
            # Replay timing is generated by the orchestrator's frozen test clock;
            # added checkpoints legitimately change that instrumentation value.
            event.pop("elapsed_ms", None)
        if event.get("type") != "card":
            continue
        card = event.get("card") or {}
        if card.get("type") != "doc":
            continue
        payload = card.get("payload") or {}
        card["title"] = "documentation result"
        card["payload"] = {
            "query": payload.get("query"),
            "scope": payload.get("scope"),
            "terms": payload.get("terms"),
        }
    return normalized


@pytest.mark.parametrize("recording", RECORDINGS, ids=lambda r: r.name)
def test_fixture_event_order_matches_contract(
    recording, fixtures_root: Path
) -> None:
    lines = (fixtures_root / f"{recording.name}.jsonl").read_text(
        encoding="utf-8"
    ).splitlines()
    events = [json.loads(line) for line in lines]
    assert events[0]["type"] == "scene"
    assert events[-1]["type"] == "done"
    assert events[-2]["type"] == "suggestions"
    caption_at = [i for i, e in enumerate(events) if e["type"] == "caption"]
    assert len(caption_at) == 1
    cards_at = [i for i, e in enumerate(events) if e["type"] == "card"]
    assert all(index < caption_at[0] for index in cards_at)
    for event in events:
        assert event["type"] in EVENT_ORDER + ("warning", "error")


@pytest.mark.parametrize("recording", RECORDINGS, ids=lambda r: r.name)
def test_fixture_cards_carry_provenance(recording, fixtures_root: Path) -> None:
    lines = (fixtures_root / f"{recording.name}.jsonl").read_text(
        encoding="utf-8"
    ).splitlines()
    for line in lines:
        event = json.loads(line)
        if event["type"] != "card":
            continue
        assert event["card"]["provenance"]
        if event["card"]["type"] == "error":
            payload = event["card"]["payload"]
            assert payload.get("expected_card")
            assert payload.get("message")
            assert "no-" in payload["message"] or "unavailable" in payload["message"]


def test_orchestrator_stops_after_max_rounds(
    store: ArtifactStore, knowledge: Knowledge
) -> None:
    call = ToolCall(id="c", name="field_metrics", args={"step": 96})
    client = FakeChatClient(rounds=[[call]] * 10, caption="Итог.")
    orchestrator = Orchestrator(
        client=client, store=store, knowledge=knowledge, max_rounds=2
    )
    events = list(orchestrator.ask("s", "что с фондом", ConsoleContext(step=96)))
    done = [event for event in events if event.type == "done"][0]
    assert done.body["tool_rounds"] == 2
    cards = [event for event in events if event.type == "card"]
    assert len(cards) == 2


def test_tool_failure_becomes_error_card(
    store: ArtifactStore, knowledge: Knowledge
) -> None:
    call = ToolCall(id="c", name="well_snapshot", args={"well": "45"})
    client = FakeChatClient(rounds=[[call]], caption="Такой скважины нет.")
    orchestrator = Orchestrator(client=client, store=store, knowledge=knowledge)
    events = list(orchestrator.ask("s", "что со скважиной 45", ConsoleContext(step=1)))
    cards = [event for event in events if event.type == "card"]
    assert len(cards) == 1
    assert cards[0].body["card"]["type"] == "error"
    assert "well 45" in cards[0].body["card"]["payload"]["message"]
    assert cards[0].body["card"].get("action") is None
    assert any(event.type == "done" for event in events)


def test_overall_deadline_interrupts_cooperative_sync_tool(
    store: ArtifactStore, knowledge: Knowledge, monkeypatch: pytest.MonkeyPatch
) -> None:
    stopped = threading.Event()

    def slow_handler(context, _arguments):
        while True:
            try:
                context.check_cancelled()
            except TimeoutError:
                stopped.set()
                raise
            time.sleep(0.005)

    monkeypatch.setitem(HANDLERS, "field_metrics", slow_handler)
    client = FakeChatClient(
        rounds=[[ToolCall(id="field", name="field_metrics", args={"step": 1})]],
        caption="The field overview is ready.",
    )
    orchestrator = Orchestrator(
        client=client, store=store, knowledge=knowledge, timeout=0.15
    )

    emitted = []
    with pytest.raises(TimeoutError, match="time budget"):
        for event in orchestrator.ask("slow-tool", "show the field", ConsoleContext()):
            emitted.append(event)

    assert stopped.is_set()
    assert not any(event.type == "card" for event in emitted)


def test_orchestrator_drops_unverified_well_and_step_references(
    store: ArtifactStore, knowledge: Knowledge
) -> None:
    call = ToolCall(id="c", name="well_snapshot", args={"well": "13"})
    client = FakeChatClient(
        rounds=[[call]], caption="Well 999 at step 999 had a liquid rate of 112.9."
    )
    orchestrator = Orchestrator(client=client, store=store, knowledge=knowledge)

    events = list(
        orchestrator.ask(
            "s", "show well 13", ConsoleContext(scenario="base", step=1, lang="en")
        )
    )

    caption = next(event for event in events if event.type == "caption")
    assert caption.body["text"] == "The rule, well, step, or date is not confirmed by this answer's evidence."
    assert any(
        event.type == "warning"
        and event.body["code"] == "context-reference-unverified"
        for event in events
    )


def test_orchestrator_drops_date_outside_active_timeline(
    store: ArtifactStore, knowledge: Knowledge
) -> None:
    call = ToolCall(id="well", name="well_snapshot", args={"well": "13"})
    client = FakeChatClient(
        rounds=[[call]], caption="Well 13 on 2040-01-01 shows a liquid rate."
    )
    orchestrator = Orchestrator(client=client, store=store, knowledge=knowledge)

    events = list(
        orchestrator.ask(
            "s", "Show well 13", ConsoleContext(scenario="base", step=1, lang="en")
        )
    )

    caption = next(event for event in events if event.type == "caption")
    assert caption.body["text"] == "The rule, well, step, or date is not confirmed by this answer's evidence."


def test_orchestrator_does_not_claim_success_when_every_tool_refuses(
    store: ArtifactStore, knowledge: Knowledge
) -> None:
    call = ToolCall(id="council", name="council_step", args={})
    client = FakeChatClient(
        rounds=[[call]], caption="The council completed allocation for this step."
    )
    orchestrator = Orchestrator(client=client, store=store, knowledge=knowledge)

    events = list(
        orchestrator.ask(
            "s", "Show the council decision", ConsoleContext(scenario="base", step=0, lang="en")
        )
    )

    card = next(event for event in events if event.type == "card")
    caption = next(event for event in events if event.type == "caption")
    warnings = [event.body["code"] for event in events if event.type == "warning"]
    assert card.body["card"]["type"] == "error"
    assert "completed allocation" not in caption.body["text"]
    assert "no-council-step" in caption.body["text"]
    assert "tool-result-unverified" in warnings


def test_orchestrator_keeps_successful_facts_and_drops_partial_failure_claim(
    store: ArtifactStore, knowledge: Knowledge
) -> None:
    calls = [
        ToolCall(id="metrics", name="field_metrics", args={}),
        ToolCall(id="council", name="council_step", args={}),
    ]
    client = FakeChatClient(
        rounds=[calls],
        caption="Field metrics returned data. The council completed allocation.",
    )
    orchestrator = Orchestrator(client=client, store=store, knowledge=knowledge)

    events = list(
        orchestrator.ask(
            "s", "Show field data and council decision", ConsoleContext(scenario="base", step=0, lang="en")
        )
    )

    cards = [event.body["card"] for event in events if event.type == "card"]
    caption = next(event for event in events if event.type == "caption")
    assert [card["type"] for card in cards] == ["metric", "error"]
    assert caption.body["text"] == "Field metrics returned data."


def test_decision_question_uses_selected_step_and_supplies_date_to_model(
    store: ArtifactStore, knowledge: Knowledge
) -> None:
    call = ToolCall(id="journal", name="decision_journal", args={})
    client = FakeChatClient(
        rounds=[[call]],
        caption="На шаге 10 (2007-11-01) журнал фиксирует команду.",
    )
    orchestrator = Orchestrator(client=client, store=store, knowledge=knowledge)

    events = list(
        orchestrator.ask(
            "s",
            "Почему выбрали этот режим?",
            ConsoleContext(
                scenario="whatif-injection-cut",
                selected_well="13",
                step=10,
            ),
        )
    )

    card_event = next(event for event in events if event.type == "card")
    card = card_event.body["card"]["payload"]
    assert card["well"] == "13"
    assert card["step"] == 10
    assert card["date"] == "2007-11-01"
    _, system_prompt = client.calls[0]
    assert "явно назови шаг и дату" in system_prompt
    assert "короткое объяснение только по записанным фактам" in system_prompt
    assert "если по истории нельзя однозначно установить нужный прогон" in system_prompt.casefold()
    assert "покажи варианты и уточни" in system_prompt.casefold()
    assert "точную причину из message" in system_prompt
    assert "предложи next_step" in system_prompt
    assert "не утверждай, что запрошенный результат получен" in system_prompt.casefold()
    messages, _ = client.calls[1]
    assert any(
        "2007-11-01" in (message.content or "")
        and message.role == "tool"
        for message in messages
    )
    caption = next(event for event in events if event.type == "caption")
    assert caption.body["text"] == "На шаге 10 (2007-11-01) журнал фиксирует команду."


def test_unnamed_neighbour_follow_up_offers_measured_links(
    store: ArtifactStore, knowledge: Knowledge
) -> None:
    client = FakeChatClient(
        rounds=[],
        caption="Связи показаны на карте. Выберите скважину для продолжения.",
    )
    orchestrator = Orchestrator(client=client, store=store, knowledge=knowledge)

    events = list(
        orchestrator.ask(
            "s",
            "А у соседней?",
            ConsoleContext(scenario="base", selected_well="1", step=96),
        )
    )

    card_event = next(event for event in events if event.type == "card")
    card = card_event.body["card"]
    assert card["type"] == "field-map"
    payload = card["payload"]
    assert payload["focus"] == ["1"]
    assert payload["edges"]
    assert all(edge["neighbour"] in payload["highlight"] for edge in payload["edges"])
    assert card["action"]["workspace"] == "field"
    assert card["action"]["view"] == "maps"
    messages, prompt = client.calls[0]
    assert "вызови connectivity для выбранной скважины" in prompt
    assert any(
        message.role == "user"
        and "Tool connectivity returned" in (message.content or "")
        and "\"edges\"" in (message.content or "")
        for message in messages
    )
    caption = next(event for event in events if event.type == "caption")
    assert caption.body["text"] == "Связи показаны на карте. Выберите скважину для продолжения."


def test_neighbour_preset_requires_a_selected_well_and_no_named_alternative() -> None:
    context = ConsoleContext(selected_well="1")

    assert _contextual_tool_preset("А у соседней?", context) == (
        ("connectivity", {"well": "1"}),
    )
    assert _contextual_tool_preset("Почему не соседняя скважина 5?", context) == ()
    assert _contextual_tool_preset("А у соседней?", ConsoleContext()) == ()


def test_here_follow_up_uses_only_the_active_well_and_step() -> None:
    context = ConsoleContext(scenario="base", selected_well="2", step=96)

    assert _contextual_tool_preset("А здесь?", context) == (
        ("well_snapshot", {"well": "2", "step": 96}),
    )
    assert _contextual_tool_preset("What here?", context) == (
        ("well_snapshot", {"well": "2", "step": 96}),
    )
    assert _contextual_tool_preset("А здесь?", ConsoleContext(step=96)) == ()
    assert _contextual_tool_preset("А на скважине 5?", context) == ()


def test_earlier_preset_repeats_well_snapshot_at_previous_control_step() -> None:
    context = ConsoleContext(scenario="base", selected_well="2", step=96)
    session = SessionStore().get("temporal-follow-up", context)
    session.remember(
        Exchange(
            question="Покажи скважину 2",
            card_types=("well",),
            caption="Скважина 2 на выбранном шаге.",
        )
    )

    assert _contextual_tool_preset("А раньше?", context, session) == (
        ("well_snapshot", {"well": "2", "step": 95}),
    )
    assert _contextual_tool_preset("А раньше?", context) == ()
    assert _contextual_tool_preset(
        "А раньше?", ConsoleContext(scenario="base", selected_well="2", step=0), session
    ) == ()


def test_selected_neighbour_follow_up_reads_that_well_at_active_step(
    store: ArtifactStore, knowledge: Knowledge
) -> None:
    sessions = SessionStore()
    context = ConsoleContext(scenario="base", selected_well="1", step=96)
    first = Orchestrator(
        client=FakeChatClient(
            rounds=[],
            caption="Выберите измеренную связанную скважину.",
        ),
        store=store,
        knowledge=knowledge,
        sessions=sessions,
    )
    first_events = list(first.ask("s", "А у соседней?", context))
    link_card = next(event for event in first_events if event.type == "card").body["card"]
    selected_neighbour = link_card["payload"]["edges"][0]["neighbour"]

    second_client = FakeChatClient(
        rounds=[[ToolCall(id="snapshot", name="well_snapshot", args={"well": selected_neighbour})]],
        caption="Снимок выбранной скважины открыт на активном шаге.",
    )
    second = Orchestrator(
        client=second_client,
        store=store,
        knowledge=knowledge,
        sessions=sessions,
    )
    second_events = list(
        second.ask("s", f"Посмотри скважину {selected_neighbour}.", context)
    )

    snapshot = next(event for event in second_events if event.type == "card").body["card"]
    assert snapshot["type"] == "well"
    assert snapshot["payload"]["well"] == selected_neighbour
    assert snapshot["payload"]["step"] == 96
    assert snapshot["payload"]["date"]
    second_messages, second_prompt = second_client.calls[1]
    assert "шаг" in second_prompt
    assert any("А у соседней?" in (message.content or "") for message in second_messages)
    assert any(
        message.role == "tool" and f'"well": "{selected_neighbour}"' in (message.content or "")
        for message in second_messages
    )


def test_here_follow_up_reads_the_selected_well_at_the_active_step(
    store: ArtifactStore, knowledge: Knowledge
) -> None:
    client = FakeChatClient(rounds=[], caption="Текущий снимок выбранной скважины.")
    orchestrator = Orchestrator(client=client, store=store, knowledge=knowledge)
    events = list(
        orchestrator.ask(
            "here-follow-up",
            "А здесь?",
            ConsoleContext(scenario="base", selected_well="2", step=96),
        )
    )

    cards = [event.body["card"] for event in events if event.type == "card"]
    assert len(cards) == 1
    assert cards[0]["type"] == "well"
    assert cards[0]["payload"]["well"] == "2"
    assert cards[0]["payload"]["step"] == 96
    assert cards[0]["payload"]["date"]


def test_unknown_tool_becomes_error_card(
    store: ArtifactStore, knowledge: Knowledge
) -> None:
    call = ToolCall(id="c", name="launch_rocket", args={})
    client = FakeChatClient(rounds=[[call]], caption="Такого нет.")
    orchestrator = Orchestrator(client=client, store=store, knowledge=knowledge)
    events = list(orchestrator.ask("s", "запусти ракету", ConsoleContext()))
    cards = [event for event in events if event.type == "card"]
    assert cards[0].body["card"]["type"] == "error"


def test_invented_number_produces_warning(
    store: ArtifactStore, knowledge: Knowledge
) -> None:
    call = ToolCall(id="c", name="field_metrics", args={"step": 96})
    client = FakeChatClient(
        rounds=[[call]], caption="Фонд заработал 777 555 руб. за шаг."
    )
    orchestrator = Orchestrator(client=client, store=store, knowledge=knowledge)
    events = list(orchestrator.ask("s", "сколько заработали", ConsoleContext(step=96)))
    warnings = [event for event in events if event.type == "warning"]
    assert warnings and warnings[0].body["code"] == "number-dropped"
    caption = [event for event in events if event.type == "caption"][0]
    assert "777 555" not in caption.body["text"]
    assert caption.body["guarded"] is True


def test_unverified_run_reference_is_removed_with_a_warning(
    store: ArtifactStore, knowledge: Knowledge
) -> None:
    client = FakeChatClient(rounds=[], caption="Прогон made-up-run-2035 выбран.")
    orchestrator = Orchestrator(client=client, store=store, knowledge=knowledge)

    events = list(orchestrator.ask("s", "Какой прогон выбран?", ConsoleContext()))

    warnings = [event for event in events if event.type == "warning"]
    caption = next(event for event in events if event.type == "caption")
    assert any(event.body["code"] == "run-reference-unverified" for event in warnings)
    assert "made-up-run-2035" not in caption.body["text"]
    assert "не подтверждён" in caption.body["text"]


def test_cancel_stops_the_stream(store: ArtifactStore, knowledge: Knowledge) -> None:
    sessions = SessionStore()
    call = ToolCall(id="c", name="field_metrics", args={"step": 96})
    client = FakeChatClient(rounds=[[call]] * 3, caption="Итог.")
    orchestrator = Orchestrator(
        client=client, store=store, knowledge=knowledge, sessions=sessions
    )
    stream = orchestrator.ask("s", "что с фондом", ConsoleContext(step=96))
    collected = [next(stream), next(stream)]
    sessions.cancel("s")
    collected.extend(stream)
    assert collected[-1].type == "error"
    assert collected[-1].body["code"] == "cancelled"


def test_cancel_during_tool_discards_its_result_and_skips_later_tools(
    store: ArtifactStore, knowledge: Knowledge, monkeypatch: pytest.MonkeyPatch
) -> None:
    entered_tool = threading.Event()
    release_tool = threading.Event()
    calls: list[str] = []

    def blocking_tool(_context: object, call: ToolCall) -> tuple[object, dict[str, object]]:
        calls.append(call.name)
        entered_tool.set()
        assert release_tool.wait(2)
        return SimpleNamespace(as_dict=lambda: {"type": "metric", "payload": {}}), {}

    monkeypatch.setattr("backend.contexts.assistant.application.orchestrator.call_tool", blocking_tool)
    sessions = SessionStore()
    client = FakeChatClient(
        rounds=[[
            ToolCall(id="first", name="field_metrics", args={"step": 0}),
            ToolCall(id="second", name="field_events", args={"from_step": 0, "to_step": 1}),
        ]],
        caption="Finished.",
    )
    orchestrator = Orchestrator(client=client, store=store, knowledge=knowledge, sessions=sessions)
    stream = orchestrator.ask("cancel-tool", "show metrics", ConsoleContext(step=0))
    events: list[object] = []
    reader = threading.Thread(target=lambda: events.extend(stream), daemon=True)
    reader.start()
    try:
        assert entered_tool.wait(1)
        sessions.cancel("cancel-tool")
    finally:
        release_tool.set()
    reader.join(timeout=2)

    assert not reader.is_alive()
    assert calls == ["field_metrics"]
    assert not any(getattr(event, "type", None) == "card" for event in events)
    assert events[-1].type == "error"
    assert events[-1].body["code"] == "cancelled"


def test_cooperative_sync_tool_stops_on_generation_cancellation(
    store: ArtifactStore, knowledge: Knowledge, monkeypatch: pytest.MonkeyPatch
) -> None:
    entered_tool = threading.Event()
    calls: list[str] = []

    def cooperative_tool(context: object, call: ToolCall) -> tuple[object, dict[str, object]]:
        calls.append(call.name)
        entered_tool.set()
        token = getattr(context, "cancellation")
        assert token is not None
        while not token.cancelled:
            threading.Event().wait(0.005)
        return SimpleNamespace(as_dict=lambda: {"type": "metric", "payload": {}}), {}

    monkeypatch.setattr("backend.contexts.assistant.application.orchestrator.call_tool", cooperative_tool)
    sessions = SessionStore()
    client = FakeChatClient(
        rounds=[[
            ToolCall(id="first", name="field_metrics", args={"step": 0}),
            ToolCall(id="second", name="field_events", args={"from_step": 0, "to_step": 1}),
        ]],
        caption="Finished.",
    )
    orchestrator = Orchestrator(client=client, store=store, knowledge=knowledge, sessions=sessions)
    stream = orchestrator.ask("cooperative-cancel", "show metrics", ConsoleContext(step=0))
    events: list[object] = []
    reader = threading.Thread(target=lambda: events.extend(stream), daemon=True)
    reader.start()
    assert entered_tool.wait(1)
    sessions.cancel("cooperative-cancel")
    reader.join(timeout=1)

    assert not reader.is_alive()
    assert calls == ["field_metrics"]
    assert events[-1].type == "error"
    assert events[-1].body["code"] == "cancelled"


def test_new_generation_cancels_old_stream_without_finishing_new_request(
    store: ArtifactStore, knowledge: Knowledge
) -> None:
    sessions = SessionStore()
    orchestrator = Orchestrator(
        client=FakeChatClient(rounds=[], caption="Новый ответ."),
        store=store,
        knowledge=knowledge,
        sessions=sessions,
    )
    old_stream = orchestrator.ask("same-session", "Старый вопрос", ConsoleContext(step=10))
    assert next(old_stream).type == "scene"
    new_stream = orchestrator.ask("same-session", "Новый вопрос", ConsoleContext(step=96))
    assert next(new_stream).type == "scene"

    old_tail = list(old_stream)
    assert old_tail[-1].type == "error"
    assert old_tail[-1].body["code"] == "cancelled"
    assert sessions.get("same-session").running is True

    new_tail = list(new_stream)
    assert new_tail[-1].type == "done"
    assert sessions.get("same-session").running is False


def test_session_remembers_the_exchange(
    store: ArtifactStore, knowledge: Knowledge
) -> None:
    sessions = SessionStore()
    call = ToolCall(id="c", name="field_metrics", args={"step": 96})
    client = FakeChatClient(rounds=[[call]], caption="Фонд работает.")
    orchestrator = Orchestrator(
        client=client, store=store, knowledge=knowledge, sessions=sessions
    )
    list(orchestrator.ask("s", "что с фондом", ConsoleContext(step=96)))
    session = sessions.get("s")
    assert len(session.history) == 1
    assert session.history[0].card_types == ("metric",)
    assert session.history[0].caption == "Фонд работает."


def test_history_is_passed_to_the_model(
    store: ArtifactStore, knowledge: Knowledge
) -> None:
    sessions = SessionStore()
    call = ToolCall(id="c", name="field_metrics", args={"step": 96})
    client = FakeChatClient(rounds=[[call]], caption="Фонд работает.")
    orchestrator = Orchestrator(
        client=client, store=store, knowledge=knowledge, sessions=sessions
    )
    list(orchestrator.ask("s", "что с фондом", ConsoleContext(step=96)))
    second = FakeChatClient(rounds=[[call]], caption="И сейчас работает.")
    again = Orchestrator(
        client=second, store=store, knowledge=knowledge, sessions=sessions
    )
    list(again.ask("s", "а сейчас", ConsoleContext(step=96)))
    first_messages = second.calls[0][0]
    assert any("Earlier in this session" in (m.content or "") for m in first_messages)


def test_empty_question_refused(store: ArtifactStore, knowledge: Knowledge) -> None:
    orchestrator = Orchestrator(
        client=FakeChatClient(rounds=[], caption=""),
        store=store,
        knowledge=knowledge,
    )
    with pytest.raises(SessionError):
        list(orchestrator.ask("s", "   ", ConsoleContext()))

@pytest.mark.parametrize("failure", ["upstream", "timeout", "cancelled"])
def test_terminal_typed_failure_is_archived_for_reload(store, knowledge, tmp_path, failure):
    from backend.contexts.assistant.domain.errors import UpstreamError
    from backend.contexts.assistant.infrastructure.session_store import SessionDisk
    class FailingClient(FakeChatClient):
        def stream(self, *args, **kwargs):
            if failure == "timeout":
                raise TimeoutError("deadline elapsed")
            raise UpstreamError("provider unavailable", code="cancelled" if failure == "cancelled" else UpstreamError.default_code)
            yield
    disk = SessionDisk(tmp_path / "sessions")
    client = FailingClient(rounds=[], caption="")
    with pytest.raises((TimeoutError, UpstreamError)):
        list(Orchestrator(client=client, store=store, knowledge=knowledge, disk=disk).ask("failed", "Hello", ConsoleContext()))
    archived = SessionDisk(tmp_path / "sessions").events("failed")
    error = next(event for event in archived if event["type"] == "error")
    assert error["code"] == {"timeout": "timeout", "upstream": UpstreamError.default_code, "cancelled": "cancelled"}[failure]
    assert not any(event["type"] == "done" for event in archived)


def test_explicit_journal_caption_only_still_contains_full_recorded_answer(store, knowledge, monkeypatch):
    from backend.contexts.assistant.application.tools.context import Card
    payload = json.loads((Path(__file__).parent / "fixtures/journal_s10.json").read_text())
    card = Card(type="rule", title="Журнал", payload=payload, provenance="recorded-generation-journal")
    monkeypatch.setattr("backend.contexts.assistant.application.orchestrator_compose.run_tool", lambda *args: card)
    console = ConsoleContext(run_id=payload["run_id"], selected_well="62", step=0)
    question = "Раскрой журнал решений этой скважины"
    assert _contextual_tool_preset(question, console)
    events = list(Orchestrator(client=FakeChatClient(rounds=[], caption="Журнал показан на карточке."), store=store, knowledge=knowledge).ask("full-journal", question, console))
    answer = next(event.body for event in events if event.type == "answer")
    assert "35 м³/сут" in answer["text"] and "`SET_RATE` 1 м³/сут" in answer["text"]
    assert answer["provenance"] == "recorded-generation-journal"
    assert next(event for event in events if event.type == "done").body.get("completion") != "recorded-journal-fallback"


def test_actual_generation_cancel_is_archived_for_reload(store, knowledge, tmp_path):
    from backend.contexts.assistant.infrastructure.session_store import SessionDisk
    disk = SessionDisk(tmp_path / "sessions")
    sessions = SessionStore()
    orchestrator = Orchestrator(client=FakeChatClient(rounds=[], caption="unused"), store=store, knowledge=knowledge, sessions=sessions, disk=disk)
    stream = orchestrator.ask("cancel-replay", "Hello", ConsoleContext())
    assert next(stream).type == "scene"
    sessions.cancel("cancel-replay")
    tail = list(stream)
    assert tail[-1].type == "error" and tail[-1].body["code"] == "cancelled"
    assert SessionDisk(tmp_path / "sessions").events("cancel-replay")[-1]["code"] == "cancelled"


def test_archived_cancel_targets_old_scene_after_new_ask_starts(store, knowledge, tmp_path):
    from backend.contexts.assistant.infrastructure.session_store import SessionDisk
    disk = SessionDisk(tmp_path / "sessions")
    orchestrator = Orchestrator(client=FakeChatClient(rounds=[], caption="Новый ответ."), store=store, knowledge=knowledge, disk=disk)
    old = orchestrator.ask("race", "Старый вопрос", ConsoleContext())
    old_scene = next(old).body["scene_id"]
    new = orchestrator.ask("race", "Новый вопрос", ConsoleContext())
    new_scene = next(new).body["scene_id"]
    list(old)
    archived_error = next(event for event in disk.events("race") if event["type"] == "error")
    assert archived_error["scene_id"] == old_scene
    assert archived_error["scene_id"] != new_scene
    assert list(new)[-1].type == "done"


def test_overflow_memory_does_not_call_slow_summary_provider_and_survives_reload(store, knowledge, tmp_path):
    from backend.contexts.assistant.infrastructure.session_store import SessionDisk
    from backend.contexts.assistant.domain.session import HISTORY_LIMIT, SUMMARY_LIMIT
    from backend.contexts.assistant.infrastructure.llm.chat_events import TextDelta, Done
    disk = SessionDisk(tmp_path / "sessions")
    for index in range(HISTORY_LIMIT):
        for event in ({"type": "ask", "question": f"Записанный вопрос {index}"},
                      {"type": "caption", "text": f"Наблюдение {index}: 35 м³/сут"}):
            disk.append("overflow", event)
    class SlowSummaryClient(FakeChatClient):
        summary_calls = 0
        def stream(self, messages, *args, **kwargs):
            if any("Сожми эти обмены" in str(message.content) for message in messages):
                self.summary_calls += 1
                time.sleep(0.15)
                yield TextDelta("Непроверенная новая справка 999999.")
                yield Done()
                return
            yield from super().stream(messages, *args, **kwargs)
    client = SlowSummaryClient(rounds=[], caption="Новый ответ.")
    orchestrator = Orchestrator(client=client, store=store, knowledge=knowledge, disk=disk)
    started = time.monotonic()
    events = list(orchestrator.ask("overflow", "Новый вопрос", ConsoleContext()))
    elapsed = time.monotonic() - started
    assert events[-1].type == "done"
    assert client.summary_calls == 0, "ready answer must not wait for a second LLM memory request"
    assert elapsed < 0.1
    session = orchestrator.sessions.get("overflow")
    assert "35 м³/сут" in session.summary_text and "999999" not in session.summary_text
    assert len(session.summary_text) <= SUMMARY_LIMIT and len(session.history) == HISTORY_LIMIT
    restarted = SessionStore(disk=SessionDisk(tmp_path / "sessions")).get("overflow")
    assert restarted.summary_text == session.summary_text
    assert restarted.summary() == session.summary()
    assert any(event.get("text") == "Наблюдение 0: 35 м³/сут" for event in disk.events("overflow"))
