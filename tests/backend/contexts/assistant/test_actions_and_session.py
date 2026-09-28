from __future__ import annotations

import pytest
from datetime import datetime, timedelta, timezone
import json

from backend.contexts.assistant.infrastructure.artifacts import ArtifactStore
from backend.contexts.assistant.infrastructure.session_store import SessionDisk
from backend.contexts.assistant.domain.errors import SessionDiskError
from backend.contexts.assistant.infrastructure.prompt import build_system_prompt
from backend.contexts.assistant.domain.session import (
    Exchange,
    SessionError,
    SessionStore,
    check_question,
)
from backend.contexts.assistant.application.suggestions import SUGGESTION_COUNT, build_suggestions
from backend.contexts.assistant.application.tools.actions import (
    ROUTE_BY_CARD,
    WORKSPACE_VIEWS,
    RouteError,
    build_action,
    check_route,
)
from backend.contexts.assistant.application.tools.context import ConsoleContext

EXPECTED_VIEWS = {
    "overview": ("fund",),
    "field": ("projection", "maps"),
    "history": ("matrix", "wall", "table"),
    "decisions": ("council", "rules"),
    "money": ("rank", "comparison", "constraints"),
}


def test_workspace_views_match_console_context() -> None:
    assert WORKSPACE_VIEWS == EXPECTED_VIEWS


def test_session_events_and_summary_survive_a_store_restart(tmp_path) -> None:
    root = tmp_path / "sessions"
    disk = SessionDisk(root)
    events = [
        {"type": "ask", "question": "Скважина 10?"},
        {"type": "card", "card": {"type": "well"}},
        {"type": "caption", "text": "Подпись"},
        {"type": "answer", "text": "Подробный ответ"},
    ]
    for event in events:
        disk.append("persisted-session", event, "ru")
    disk.set_summary("persisted-session", "Краткий контекст")

    restarted_disk = SessionDisk(root)
    restored = SessionStore(disk=restarted_disk).get("persisted-session")

    assert restarted_disk.events("persisted-session") == events
    assert restarted_disk.meta("persisted-session").summary == "Краткий контекст"
    assert restored.questions() == ("Скважина 10?",)
    assert restored.history[0].card_types == ("well",)
    assert restored.history[0].caption == "Подпись"
    assert restored.history[0].answer == "Подробный ответ"


def test_scene_ids_continue_after_restart_even_when_last_answer_failed(tmp_path) -> None:
    root = tmp_path / "sessions"
    disk = SessionDisk(root)
    events = [
        {"type": "ask", "question": "Первый вопрос"},
        {"type": "scene", "scene_id": "s-04", "question": "Первый вопрос"},
        {"type": "caption", "scene_id": "s-04", "text": "Ответ"},
        {"type": "done", "scene_id": "s-04"},
        {"type": "ask", "question": "Запрос, завершившийся ошибкой"},
        {"type": "scene", "scene_id": "s-05", "question": "Запрос, завершившийся ошибкой"},
        {"type": "error", "code": "timeout"},
    ]
    for event in events:
        disk.append("restart-scene", event)
    restored = SessionStore(disk=SessionDisk(root)).get("restart-scene")
    assert restored.next_scene_id() == "s-06"


def test_replayed_duplicate_scene_ids_remain_distinct_and_stable(tmp_path) -> None:
    disk = SessionDisk(tmp_path / "sessions")
    for question in ("Первый", "Второй"):
        disk.append("duplicate-scene", {"type": "ask", "question": question})
        disk.append("duplicate-scene", {"type": "scene", "scene_id": "s-05", "question": question})
        disk.append("duplicate-scene", {"type": "caption", "scene_id": "s-05", "text": question})
    replayed = disk.events("duplicate-scene")
    assert [event["scene_id"] for event in replayed if event["type"] == "scene"] == ["s-05", "s-06"]
    assert [event["scene_id"] for event in replayed if event["type"] == "caption"] == ["s-05", "s-06"]
    disk.append("duplicate-scene", {"type": "ask", "question": "Третий"})
    disk.append("duplicate-scene", {"type": "scene", "scene_id": "s-06", "question": "Третий"})
    expanded = disk.events("duplicate-scene")
    assert expanded[:len(replayed)] == replayed
    assert expanded[-1]["scene_id"] == "s-07"
    assert SessionStore(disk=SessionDisk(disk.root)).get("duplicate-scene").next_scene_id() == "s-08"


def test_scene_watermark_survives_bounded_event_replay(tmp_path, monkeypatch) -> None:
    disk = SessionDisk(tmp_path / "sessions")
    disk.append("bounded-scene", {"type": "ask", "question": "Запрос"})
    disk.append("bounded-scene", {"type": "scene", "scene_id": "s-07"})
    monkeypatch.setattr("backend.contexts.assistant.infrastructure.session_store.MAX_EVENTS", 1)
    assert SessionStore(disk=SessionDisk(disk.root)).get("bounded-scene").next_scene_id() == "s-08"


def test_session_disk_prunes_expired_sessions_and_keeps_recent_ones(tmp_path) -> None:
    root = tmp_path / "sessions"
    disk = SessionDisk(root, retention_days=30)
    disk.append("old-session", {"type": "ask", "question": "старый вопрос"})
    disk.append("recent-session", {"type": "ask", "question": "свежий вопрос"})

    old_meta_path = root / "old-session" / "meta.json"
    old_meta = json.loads(old_meta_path.read_text(encoding="utf-8"))
    old_meta["last"] = (
        datetime.now(tz=timezone.utc) - timedelta(days=31)
    ).isoformat().replace("+00:00", "Z")
    old_meta_path.write_text(json.dumps(old_meta), encoding="utf-8")

    restarted = SessionDisk(root, retention_days=30)
    rows = restarted.listing()
    assert [row["id"] for row in rows] == ["recent-session"]
    assert rows[0]["first_question"] == "свежий вопрос"
    assert not (root / "old-session").exists()
    assert (root / "recent-session" / "events.jsonl").is_file()


def test_session_ttl_must_be_within_supported_range(tmp_path) -> None:
    with pytest.raises(SessionDiskError, match="AIOS_JARVIS_SESSION_TTL_DAYS"):
        SessionDisk(tmp_path / "sessions", retention_days=0)


def test_expired_session_is_removed_from_memory_on_resume(tmp_path) -> None:
    root = tmp_path / "sessions"
    disk = SessionDisk(root, retention_days=30)
    disk.append("resume-session", {"type": "ask", "question": "old question"})
    sessions = SessionStore(disk=disk)
    restored = sessions.get("resume-session")
    assert restored.questions() == ("old question",)

    meta_path = root / "resume-session" / "meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    meta["last"] = (
        datetime.now(tz=timezone.utc) - timedelta(days=31)
    ).isoformat().replace("+00:00", "Z")
    meta_path.write_text(json.dumps(meta), encoding="utf-8")
    disk.meta("resume-session").last = meta["last"]

    resumed = sessions.get("resume-session")
    assert resumed.questions() == ()
    assert resumed.summary_text == ""
    assert not (root / "resume-session").exists()


def test_every_card_route_is_valid() -> None:
    for card_type, (workspace, view) in ROUTE_BY_CARD.items():
        assert check_route(workspace, view) == (workspace, view), card_type


def test_field_map_action_opens_map_view_with_selected_well() -> None:
    action = build_action("field-map", {"focus": ["19"], "edges": [{"neighbour": "10"}]}, "base")
    assert action == {
        "scenario": "base",
        "workspace": "field",
        "view": "maps",
        "well": "19",
    }


def test_run_comparison_action_selects_run_without_treating_it_as_scenario() -> None:
    action = build_action(
        "compare",
        {"a": {"id": "old-run"}, "b": {"id": "jarvis-policy-20260926"}},
        "base",
        "runs",
    )
    assert action is not None
    assert action["run_id"] == "jarvis-policy-20260926"
    assert action["scenario"] == "base"


def test_run_backed_decision_action_keeps_link_provenance_separate() -> None:
    payload = {
        "run_id": "run-a",
        "well": "19",
        "step": 210,
        "run_series": {"rows": [{"step": 210}]},
        "connectivity_source": {"available": True, "scenario": "base"},
    }
    action = build_action("rule", payload, "base")
    assert action == {
        "companion_only": True,
        "run_id": "run-a",
        "scenario": "base",
        "well": "19",
        "step": 210,
        "connections_available": True,
    }


def test_run_backed_decision_without_measured_links_does_not_offer_map_links() -> None:
    payload = {
        "run_id": "run-a",
        "well": "19",
        "step": 210,
        "run_series": {"rows": [{"step": 210}]},
        "connectivity_source": {"available": False},
    }
    action = build_action("rule", payload, "base")
    assert action is not None
    assert action["companion_only"] is True
    assert "connections_available" not in action


def test_unknown_workspace_refused() -> None:
    with pytest.raises(RouteError):
        check_route("engine-room", "fund")


def test_unknown_view_refused() -> None:
    with pytest.raises(RouteError):
        check_route("field", "matrix")


def test_error_card_has_no_action() -> None:
    assert build_action("error", {}, "base") is None


def test_guide_action_carries_spotlight() -> None:
    payload = {
        "workspace": "field",
        "view": "projection",
        "controls": [{"label": "x", "spotlight": "projection-threshold-slider"}],
    }
    action = build_action("guide", payload, "base")
    assert action == {
        "scenario": "base",
        "workspace": "field",
        "view": "projection",
        "spotlight": "projection-threshold-slider",
    }


def test_glossary_action_uses_first_place() -> None:
    payload = {
        "where_in_platform": [
            {"workspace": "money", "view": "rank", "spotlight": "npv-rank-table"}
        ]
    }
    action = build_action("glossary", payload, "base")
    assert action["view"] == "rank"
    assert action["spotlight"] == "npv-rank-table"


def test_glossary_without_places_has_no_action() -> None:
    assert build_action("glossary", {"where_in_platform": []}, "base") is None


def test_check_question_trims() -> None:
    assert check_question("  что с фондом  ") == "что с фондом"


def test_empty_question_refused() -> None:
    with pytest.raises(SessionError):
        check_question("   ")


def test_too_long_question_refused() -> None:
    with pytest.raises(SessionError) as error:
        check_question("a" * 601)
    assert "601 characters" in str(error.value)


def test_session_keeps_six_exchanges() -> None:
    store = SessionStore()
    session = store.get("s1", ConsoleContext())
    for index in range(9):
        session.remember(Exchange(f"q{index}", ("well",), f"a{index}"))
    assert len(session.history) == 6
    assert session.history[0].question == "q3"


def test_session_scene_ids_increment() -> None:
    session = SessionStore().get("s2", ConsoleContext())
    assert session.next_scene_id() == "s-01"
    assert session.next_scene_id() == "s-02"


@pytest.mark.parametrize(
    ("lang", "required"),
    [
        ("ru", "явно назови шаг и дату"),
        ("en", "state its step and date"),
    ],
)
def test_decision_prompt_uses_and_names_selected_step(lang: str, required: str) -> None:
    prompt = build_system_prompt(ConsoleContext(step=96), lang)

    assert required in prompt
    assert "step is missing" in prompt if lang == "en" else "шага в контексте нет" in prompt


@pytest.mark.parametrize(
    ("lang", "follow_up_rule", "memory_rule"),
    [
        ("ru", "проверяй инструментами", "отвечай из памяти сессии"),
        ("en", "must use tools", "answer from session memory"),
    ],
)
def test_neighbour_follow_up_uses_current_tools_not_session_memory(
    lang: str, follow_up_rule: str, memory_rule: str
) -> None:
    prompt = build_system_prompt(ConsoleContext(lang=lang), lang)

    assert follow_up_rule in prompt
    assert memory_rule in prompt
    assert "neighbouring one\") - answer from the session memory" not in prompt
    assert "«а у соседней») — отвечай из памяти" not in prompt


def test_new_generation_cancels_the_previous() -> None:
    store = SessionStore()
    store.start("s3", ConsoleContext())
    assert store.is_cancelled("s3") is False
    store.cancel("s3")
    assert store.is_cancelled("s3") is True
    store.start("s3", ConsoleContext())
    assert store.is_cancelled("s3") is False


def test_old_generation_cannot_cancel_or_finish_the_new_request() -> None:
    store = SessionStore()
    session, old_generation = store.start("s4", ConsoleContext())
    _, new_generation = store.start("s4", ConsoleContext(step=96))

    assert session.generation == new_generation
    assert store.is_cancelled("s4", old_generation) is True
    assert store.is_cancelled("s4", new_generation) is False
    store.finish("s4", old_generation)
    assert session.running is True
    assert store.cancel("s4", old_generation) is False
    assert store.cancel("s4", new_generation) is True


def test_session_requires_an_id() -> None:
    with pytest.raises(SessionError):
        SessionStore().get("")


def test_suggestions_mention_the_selected_well(store: ArtifactStore) -> None:
    items = build_suggestions(
        ConsoleContext(selected_well="13", step=96), store
    )
    assert len(items) == SUGGESTION_COUNT
    assert any("13" in item["text"] for item in items)


def test_suggestions_offer_a_total_at_the_horizon_end(store: ArtifactStore) -> None:
    items = build_suggestions(ConsoleContext(step=224), store)
    assert any("ЧДД" in item["text"] for item in items)


def test_suggestions_offer_comparison_off_base(store: ArtifactStore) -> None:
    items = build_suggestions(
        ConsoleContext(scenario="whatif-injection-cut"), store
    )
    assert any("whatif-injection-cut" in item["text"] for item in items)


def test_suggestions_english(store: ArtifactStore) -> None:
    items = build_suggestions(ConsoleContext(lang="en", selected_well="13"), store)
    assert all(item["text"].isascii() for item in items)


def test_system_prompt_states_every_rule() -> None:
    prompt = build_system_prompt(
        ConsoleContext(scenario="base", step=96, selected_well="13"), "ru"
    )
    for marker in (
        "Джарвис",
        "не больше 2 фраз",
        "Ни одного числа от себя",
        "explain_term",
        "platform_guide",
        "отказ",
        "на «вы»",
        "В данных фонда этого нет",
        "Язык ответа",
    ):
        assert marker in prompt, marker


def test_system_prompt_carries_console_context() -> None:
    prompt = build_system_prompt(
        ConsoleContext(
            scenario="whatif-injection-cut",
            step=96,
            date="2015-01-01",
            selected_well="13",
            workspace="field",
            view="projection",
        )
    )
    assert "whatif-injection-cut" in prompt
    assert "96" in prompt
    assert "2015-01-01" in prompt
    assert "field/projection" in prompt


def test_system_prompt_switches_language() -> None:
    prompt = build_system_prompt(ConsoleContext(lang="en"), "en")
    assert "You are Jarvis" in prompt
    assert "The answer language is English" in prompt


def test_local_prompt_memory_is_bounded_verbatim_and_preserves_legacy_provenance():
    from backend.contexts.assistant.domain.session import Session, Exchange, HISTORY_LIMIT, SUMMARY_LIMIT, MEMORY_PREFIX
    session = Session(session_id="bounded", summary_text="Legacy summary from earlier provider")
    session.remember(Exchange("Earlier question", ("rule",), "Observed 35 m³/day", "Scheduled SET_RATE 1 m³/day"))
    for index in range(HISTORY_LIMIT):
        session.remember(Exchange(f"New question {index}", ("rule",), "Present card"))
    session.compact_memory()
    records = [json.loads(row) for row in session.summary_text[len(MEMORY_PREFIX):].splitlines()]
    assert records[0]["legacy_summary"] == "Legacy summary from earlier provider"
    assert records[-1]["caption"] == "Observed 35 m³/day"
    assert records[-1]["answer_excerpt"] == "Scheduled SET_RATE 1 m³/day"
    for index in range(100):
        session.remember(Exchange("Long question " * 300, ("rule",), 'Quoted "value"\n' * 100, "Observed 987654321 " * 100))
        session.compact_memory()
        assert len(session.summary_text) <= SUMMARY_LIMIT
        assert len(session.summary()) < 10000
        assert not session.pending_summary()
        for row in session.summary_text[len(MEMORY_PREFIX):].splitlines():
            assert isinstance(json.loads(row), dict)
    assert len(session.history) == HISTORY_LIMIT
    assert "…" in session.summary_text
