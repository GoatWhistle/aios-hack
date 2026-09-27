from __future__ import annotations

from backend.contexts.assistant.application.tools.docs import _document_url


def test_document_url_encodes_relative_source_and_section() -> None:
    assert _document_url(
        "guide folder/ARCHITECTURE.md",
        "#12-прогон",
        "https://docs.example.org/aios/",
    ) == (
        "https://docs.example.org/aios/guide%20folder/ARCHITECTURE.md#12-%D0%BF%D1%80%D0%BE%D0%B3%D0%BE%D0%BD"
    )


def test_document_url_is_disabled_for_unsafe_bases_and_paths() -> None:
    assert _document_url("README.md", "intro", "http://docs.example.org") is None

    assert _document_url("../secrets.txt", "intro", "https://docs.example.org") is None
    assert _document_url("/etc/passwd", "") is None


def test_document_url_is_absent_when_not_configured() -> None:
    assert _document_url("README.md", "intro") is None
    assert _document_url("knowledge/docs/CURRENT_SYSTEM.md", "#goal") == (
        "/jarvis/knowledge/docs/CURRENT_SYSTEM.md#goal"
    )
    assert _document_url(
        "knowledge/docs/CURRENT_SYSTEM.md",
        "#goal",
        "https://docs.example.org/",
    ) == "/jarvis/knowledge/docs/CURRENT_SYSTEM.md#goal"
