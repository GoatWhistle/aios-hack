from __future__ import annotations

from typing import Any, Mapping, Sequence
import re

__all__ = ["restore_exchanges", "normalize_scene_ids"]


def normalize_scene_ids(events: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Repair legacy repeated IDs without merging separate persisted requests.

    Allocation depends only on the prefix already read, so appending future
    requests cannot change IDs previously returned to a replaying client.
    """
    result: list[dict[str, Any]] = []
    used: set[str] = set()
    serial = 0
    active: dict[str, str] = {}
    for event in events:
        row = dict(event)
        if row.get("type") == "ask":
            active = {}
        raw_id = str(row.get("scene_id") or "")
        match = re.fullmatch(r"s-(\d+)", raw_id)
        if row.get("type") == "scene" and match is not None:
            if raw_id not in active:
                serial = max(serial, int(match.group(1)))
                if raw_id in used:
                    serial += 1
                    active[raw_id] = f"s-{serial:02d}"
                else:
                    active[raw_id] = raw_id
                used.add(active[raw_id])
        if raw_id in active:
            row["scene_id"] = active[raw_id]
        result.append(row)
    return result


def restore_exchanges(events: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    collected: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for event in events:
        kind = event.get("type")
        if kind == "ask":
            if current is not None:
                collected.append(current)
            current = {
                "question": str(event.get("question") or ""),
                "card_types": [],
                "caption": "",
                "answer": "",
            }
        elif current is None:
            continue
        elif kind == "card":
            card = event.get("card") or {}
            if isinstance(card, Mapping):
                current["card_types"].append(str(card.get("type") or ""))
        elif kind == "caption":
            current["caption"] = str(event.get("text") or "")
        elif kind == "answer":
            current["answer"] = str(event.get("text") or "")
    if current is not None:
        collected.append(current)
    return collected
