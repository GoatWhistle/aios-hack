from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.contexts.assistant.infrastructure.docs_index import load_index
from backend.contexts.assistant.infrastructure.docs_index.chunking import (
    chunks_of_markdown,
    is_snapshot_source,
)


REPOSITORY = Path(__file__).resolve().parents[4]


@pytest.fixture(scope="module")
def docs_index(tmp_path_factory):
    return load_index(
        roots=(REPOSITORY,),
        cache=tmp_path_factory.mktemp("jarvis-docs") / "index.json",
    )


@pytest.mark.parametrize(
    ("question", "source", "evidence"),
    [
        (
            "Что известно о границах применимости суррогата, OOD и переносе на новое месторождение?",
            "knowledge/docs/CURRENT_SYSTEM.md",
            ("Высокий OOD", "новые ограничения"),
        ),
        (
            "Как работают агенты R0–R7 и кто принимает решения?",
            "knowledge/docs/CURRENT_SYSTEM.md",
            ("поле", "группа", "скважина"),
        ),
        (
            "Что означает OPM OK, как отдельно проверить sound=true?",
            "knowledge/docs/CURRENT_SYSTEM.md",
            ("OPM", "sound=true"),
        ),
        (
            "Как считается ЧДД и что означает ставка WACC?",
            "knowledge/docs/NPV_METHODOLOGY.md",
            ("WACC", "FCF", "Σ_y", "DF(y)"),
        ),
        (
            "Как отличить ограничения организаторов, diagnostic и assumption в кейсе?",
            "config/README.md",
            ("diagnostic", "assumption"),
        ),
        (
            "Как карточка Джарвиса показывает происхождение данных и найденный документ?",
            "knowledge/docs/JARVIS_USER_GUIDE.md",
            ("карточк", "происхождение"),
        ),
    ],
)
def test_expert_questions_retrieve_documented_evidence(docs_index, question, source, evidence):
    hits = docs_index.search(question, k=6, scope="all")
    matching = [hit for hit in hits if hit.source == source]

    assert matching, f"{question!r} did not retrieve {source}; got {[hit.source for hit in hits]}"
    text = "\n".join(hit.text.casefold() for hit in matching)
    assert all(term.casefold() in text for term in evidence), (
        f"{question!r} retrieved {source} without all expected evidence {evidence!r}"
    )


def test_archived_sources_are_labeled_without_changing_deep_link_anchor():
    chunks = chunks_of_markdown(
        "checkpoints/2026-08-31-runbook.md",
        "# Проверка\n\nСтарый порядок действий.",
        "docs",
    )

    assert chunks[0].heading.startswith("[ИСТОРИЧЕСКИЙ / HISTORICAL]")
    assert "does not establish current system behavior" in chunks[0].text
    assert chunks[0].anchor == "#проверка"


def test_snapshot_sources_are_distinguished_from_historical_archive():
    chunks = chunks_of_markdown(
        "PROJECT_CONTEXT.md",
        "# Current snapshot\n\nA dated implementation snapshot.",
        "docs",
    )

    assert chunks[0].heading.startswith("[СНИМОК / SNAPSHOT]")
    assert "point-in-time state" in chunks[0].text
    assert is_snapshot_source("README.md")
    assert not is_snapshot_source("config/README.md")


def test_backlog_is_labeled_as_a_plan_not_current_product_behavior():
    chunks = chunks_of_markdown(
        "JARVIS_BACKLOG.md",
        "# Future work\n\nAdd a new feature.",
        "docs",
    )

    assert chunks[0].heading.startswith("[ПЛАН / PLAN]")
    assert "not verified product behavior" in chunks[0].text


def test_system_map_points_to_existing_current_files_and_indexed_sections(docs_index):
    payload = (REPOSITORY / "frontend/public/jarvis/knowledge/system.json").read_text(
        encoding="utf-8"
    )
    nodes = json.loads(payload)["nodes"]
    for node in nodes:
        assert all((REPOSITORY / item).exists() for item in node["files"]), node["id"]
        doc = node.get("doc")
        if doc:
            source = doc.split("#", 1)[0]
            assert source in docs_index.sources(), (node["id"], source)
