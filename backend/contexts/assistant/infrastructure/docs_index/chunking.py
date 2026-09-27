from __future__ import annotations

from pathlib import Path
from typing import Any, Sequence

from backend.contexts.assistant.domain.errors import KnowledgeError
from backend.contexts.assistant.domain.knowledge import LANGS
from backend.contexts.assistant.infrastructure.docs_index.models import Chunk
from backend.contexts.assistant.infrastructure.docs_index.text import (
    cut_into_pieces,
    split_sections,
    numbers_in,
    slug,
)
from backend.contexts.assistant.infrastructure.knowledge import KnowledgeStore


HISTORICAL_SOURCES = frozenset(
    {
        "AUDIT_PLAN_2026-09-08.md",
        "BACKLOG.md",
        "DISCUSSIONS.md",
        "FINAL_PLAN.md",
        "JARVIS_V2.md",
        "TASK.md",
    }
)
_HISTORICAL_SOURCE_NAMES = frozenset(item.casefold() for item in HISTORICAL_SOURCES)

SNAPSHOT_SOURCES = frozenset(
    {
        "ARCHITECTURE.md",
        "ARCHITECTURE_DIAGRAM.md",
        "JARVIS_CONTEXT.md",
        "JARVIS_RUNS_20260926.md",
        "PROJECT_CONTEXT.md",
        "README.md",
    }
)
_SNAPSHOT_SOURCE_NAMES = frozenset(item.casefold() for item in SNAPSHOT_SOURCES)

HISTORICAL_NOTICE = (
    "[ИСТОРИЧЕСКИЙ ИСТОЧНИК / HISTORICAL SOURCE: этот материал отражает план,"
    " аудит или состояние на момент подготовки и не подтверждает текущее поведение."
    " Сверяйте текущие возможности с актуальным контекстом и кодом. / This is a"
    " point-in-time plan, audit, or status record and does not establish current"
    " system behavior. Verify current capabilities against the current context and code.]"
)
SNAPSHOT_NOTICE = (
    "[СНИМОК СОСТОЯНИЯ / POINT-IN-TIME SNAPSHOT: этот документ фиксирует состояние"
    " на дату или в момент подготовки. Он полезен как контекст, но не доказывает"
    " текущее поведение; сверяйте его с актуальными документами, конфигурацией и кодом."
    " / This document records a point-in-time state. Use it as context, not as proof of"
    " current behavior; verify against current documentation, configuration, and code.]"
)
PLAN_SOURCES = frozenset({"JARVIS_BACKLOG.md"})
_PLAN_SOURCE_NAMES = frozenset(item.casefold() for item in PLAN_SOURCES)
PLAN_NOTICE = (
    "[ПЛАН / PLAN: этот документ описывает желаемый объём и статус задач, а не"
    " подтверждённые функции продукта. Проверяйте реализацию по текущему коду и тестам."
    " / This document describes intended work and task status, not verified product"
    " behavior. Check implementation against current code and tests.]"
)


def is_historical_source(source: str) -> bool:
    path = source.replace("\\", "/").casefold()
    name = path.rsplit("/", 1)[-1]
    return (
        name in _HISTORICAL_SOURCE_NAMES
        or path.startswith("checkpoints/")
        or path.startswith("8sept-audit/")
        or path.endswith(".txt")
    )


def is_snapshot_source(source: str) -> bool:
    path = source.replace("\\", "/").casefold()
    name = path.rsplit("/", 1)[-1]
    if name == "readme.md":
        return "/" not in path
    return name in _SNAPSHOT_SOURCE_NAMES


def is_plan_source(source: str) -> bool:
    name = source.replace("\\", "/").rsplit("/", 1)[-1].casefold()
    return name in _PLAN_SOURCE_NAMES


def chunks_of_markdown(source: str, text: str, scope: str) -> list[Chunk]:
    collected: list[Chunk] = []
    historical = is_historical_source(source)
    plan = not historical and is_plan_source(source)
    snapshot = not historical and not plan and is_snapshot_source(source)
    temporal_notice = (
        HISTORICAL_NOTICE
        if historical
        else PLAN_NOTICE
        if plan
        else SNAPSHOT_NOTICE
        if snapshot
        else ""
    )
    for heading, body in split_sections(text):
        title = heading or source
        anchor = slug(title.split("›")[-1].strip()) if heading else ""
        if historical:
            title = f"[ИСТОРИЧЕСКИЙ / HISTORICAL] {title}"
        elif plan:
            title = f"[ПЛАН / PLAN] {title}"
        elif snapshot:
            title = f"[СНИМОК / SNAPSHOT] {title}"
        for piece in cut_into_pieces(body):
            collected.append(
                Chunk(
                    source=source,
                    heading=title,
                    anchor=anchor,
                    text=f"{temporal_notice}\n\n{piece}" if temporal_notice else piece,
                    numbers=tuple(numbers_in(piece)),
                    scope=scope,
                )
            )
    return collected


def chunks_of_plain(source: str, text: str, scope: str) -> list[Chunk]:
    historical = is_historical_source(source)
    plan = not historical and is_plan_source(source)
    snapshot = not historical and not plan and is_snapshot_source(source)
    temporal_notice = (
        HISTORICAL_NOTICE
        if historical
        else PLAN_NOTICE
        if plan
        else SNAPSHOT_NOTICE
        if snapshot
        else ""
    )
    return [
        Chunk(
            source=source,
            heading=(
                f"[ИСТОРИЧЕСКИЙ / HISTORICAL] {source}"
                if historical
                else f"[ПЛАН / PLAN] {source}"
                if plan
                else f"[СНИМОК / SNAPSHOT] {source}"
                if snapshot
                else source
            ),
            anchor="",
            text=f"{temporal_notice}\n\n{piece}" if temporal_notice else piece,
            numbers=tuple(numbers_in(piece)),
            scope=scope,
        )
        for piece in cut_into_pieces(text.strip())
    ]


def _joined(values: Sequence[str]) -> str:
    seen: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.append(value)
    return " / ".join(seen)


def _term_text(store: KnowledgeStore, identifier: str) -> tuple[str, str]:
    per_lang = [store.term(identifier, lang) for lang in LANGS]
    present = [item for item in per_lang if item is not None]
    if not present:
        return identifier, ""
    term = present[0].term
    names = _joined([item.text.term for item in present])
    body_parts = [item.text.definition for item in present if item.text.definition]
    for key, value in (("formula", term.formula), ("unit", term.unit), ("source", term.source)):
        if value:
            body_parts.append(f"{key}: {value}")
    if term.aliases:
        body_parts.append("синонимы: " + ", ".join(term.aliases))
    return names or identifier, chr(10).join(body_parts)


def _screen_text(store: KnowledgeStore, workspace: str, view: str) -> tuple[str, str]:
    per_lang = [store.screen(workspace, view, lang) for lang in LANGS]
    present = [item for item in per_lang if item is not None]
    if not present:
        return f"({workspace}/{view})", ""
    names = _joined([item.text.title for item in present])
    parts: list[str] = []
    for item in present:
        for value in (item.text.what, item.text.how_to_read):
            if value:
                parts.append(value)
    controls = present[0].screen.controls
    for index, control in enumerate(controls):
        labels = _joined([_at_index(item.text.controls, index) for item in present])
        parts.append(
            f"элемент: {labels}"
            + (f" — горячая клавиша {control.hotkey}" if control.hotkey else "")
            + (f" — якорь {control.spotlight}" if control.spotlight else "")
        )
    for item in present:
        parts.extend(item.text.questions)
    return f"{names} ({workspace}/{view})", chr(10).join(part for part in parts if part)


def _element_text(store: KnowledgeStore, identifier: str) -> tuple[str, str]:
    per_lang: list[Any] = []
    for lang in LANGS:
        for element in store.elements(lang):
            if element.id == identifier:
                per_lang.append(element)
    if not per_lang:
        return identifier, ""
    names = _joined([item.text.title for item in per_lang])
    parts: list[str] = []
    for item in per_lang:
        for value in (item.text.what, item.text.how_to_read):
            if value:
                parts.append(value)
    controls = per_lang[0].element.controls
    for index in range(len(controls)):
        parts.append(_joined([_at_index(item.text.controls, index) for item in per_lang]))
    return names or identifier, chr(10).join(part for part in parts if part)


def _at_index(values: Sequence[str], index: int) -> str:
    return values[index] if index < len(values) else ""


def chunks_of_knowledge(root: Path) -> list[Chunk]:
    try:
        store = KnowledgeStore(root)
    except KnowledgeError:
        return []
    collected: list[Chunk] = []
    for term in store.localized("ru"):
        heading, body = _term_text(store, term.id)
        if not body:
            continue
        collected.append(
            Chunk(
                source="knowledge/glossary.json",
                heading=heading,
                anchor=slug(term.id),
                text=heading + chr(10) + body,
                numbers=tuple(numbers_in(body)),
                scope="knowledge",
            )
        )
    for screen in store.screens("ru"):
        heading, body = _screen_text(store, screen.workspace, screen.view)
        collected.append(
            Chunk(
                source="knowledge/guide.json",
                heading=heading,
                anchor=slug(f"{screen.workspace}-{screen.view}"),
                text=heading + chr(10) + body,
                numbers=tuple(numbers_in(body)),
                scope="knowledge",
            )
        )
    for element in store.elements("ru"):
        heading, body = _element_text(store, element.id)
        if not body:
            continue
        collected.append(
            Chunk(
                source="knowledge/guide.json",
                heading=heading,
                anchor=slug(element.id),
                text=heading + chr(10) + body,
                numbers=tuple(numbers_in(body)),
                scope="knowledge",
            )
        )
    return collected
