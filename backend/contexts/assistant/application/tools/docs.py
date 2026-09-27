from __future__ import annotations

from pathlib import PurePosixPath
from typing import Any, Mapping
from urllib.parse import quote, urlsplit

from backend.contexts.assistant.infrastructure.docs_index import (
    DEFAULT_K,
    MAX_K,
    DocsIndexError,
    shared_index,
)
from backend.contexts.assistant.application.tools.context import Card, ToolContext, ToolFailure
from backend.shared.settings import Settings

PROVENANCE = "docs"
NO_HITS = "no-doc-hits"
DOCS_BASE_URL_ENV = "AIOS_JARVIS_DOCS_BASE_URL"


def _document_url(source: str, anchor: str, base_url: str | None = None) -> str | None:
    path = PurePosixPath(source)
    if path.is_absolute() or any(part in ("", ".", "..") for part in path.parts):
        return None
    suffix = "/".join(quote(part, safe="") for part in path.parts)
    if source.startswith("knowledge/docs/"):
        url = f"/jarvis/{suffix}"
        encoded_anchor = quote(anchor.removeprefix("#"), safe="-_")
        return f"{url}#{encoded_anchor}" if anchor else url
    base = (base_url or "").strip().rstrip("/")
    if not base:
        return None
    parsed = urlsplit(base)
    local_http = parsed.scheme == "http" and parsed.hostname in {
        "localhost", "127.0.0.1", "::1",
    }
    if (
        not parsed.hostname
        or (parsed.scheme != "https" and not local_http)
        or parsed.username or parsed.password or parsed.query or parsed.fragment
    ):
        return None
    url = f"{base}/{suffix}"
    encoded_anchor = quote(anchor.removeprefix("#"), safe="-_")
    return f"{url}#{encoded_anchor}" if anchor else url


def _index(context: ToolContext) -> Any:
    if context.docs is not None:
        return context.docs
    return shared_index()


def search_docs(context: ToolContext, arguments: Mapping[str, Any]) -> Card:
    query = str(arguments.get("query") or "").strip()
    if not query:
        raise ToolFailure(
            "the documentation query is empty: there is nothing to search for, name "
            "the topic with words from the question"
        )
    scope = str(arguments.get("scope") or "all")
    requested = arguments.get("k")
    k = int(requested) if isinstance(requested, (int, float)) else DEFAULT_K
    k = max(1, min(k, MAX_K))
    index = _index(context)
    docs_base_url = Settings.from_env().raw.get(DOCS_BASE_URL_ENV)
    try:
        hits = index.search(query, k, scope)
    except DocsIndexError as error:
        raise ToolFailure(str(error)) from error
    if not hits:
        raise ToolFailure(
            f"{NO_HITS}: the documentation index ({index.size()} chunks from "
            f"{len(index.sources())} files) holds no match for the query "
            f"{query!r} in scope {scope}; the content of documents must not "
            "be invented"
        )
    head = hits[0]
    payload: dict[str, Any] = {
        "query": query,
        "scope": scope,
        "terms": _terms(query),
        "hits": [
            {
                **hit.as_dict(),
                **(
                    {"url": url}
                    if (url := _document_url(hit.source, hit.anchor, docs_base_url)) is not None
                    else {}
                ),
            }
            for hit in hits
        ],
        "indexed_chunks": index.size(),
        "indexed_files": len(index.sources()),
    }
    return Card(
        type="doc",
        title=_title(head.source, head.heading),
        payload=payload,
        provenance=PROVENANCE,
    )


def _terms(query: str) -> list[str]:
    words: list[str] = []
    for raw in query.replace("«", " ").replace("»", " ").split():
        cleaned = raw.strip(".,;:!?()[]{}\"'—–-")
        if len(cleaned) >= 3 and cleaned not in words:
            words.append(cleaned)
    return words


def _title(source: str, heading: str) -> str:
    tail = heading.split("›")[-1].strip()
    if not tail or tail == source:
        return source
    return f"{source} › {tail}"
