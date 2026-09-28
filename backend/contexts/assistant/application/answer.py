from __future__ import annotations

import re
from dataclasses import dataclass

ANSWER_MARKER = "---ОТВЕТ---"
ANSWER_MARKER_EN = "---ANSWER---"
MARKER_PATTERN = re.compile(
    r"^[ \t]*-{2,}\s*(?:ОТВЕТ|ANSWER)\s*-{2,}[ \t]*$", re.IGNORECASE | re.MULTILINE
)
ANSWER_LIMIT = 1500
PROTECTED_MARKDOWN = re.compile(
    r"```[^\n]*\n.*?(?:```|\Z)|`[^`\n]*`|\[[^\]\n]*\]\([^)]*\)",
    re.DOTALL,
)


@dataclass(frozen=True, slots=True)
class Split:
    caption: str
    answer: str | None


def split_answer(text: str) -> Split:
    match = MARKER_PATTERN.search(text)
    if match is None:
        return Split(caption=text.strip(), answer=None)
    caption = text[: match.start()].strip()
    answer = text[match.end() :].strip()
    if not answer:
        return Split(caption=caption, answer=None)
    return Split(caption=caption, answer=_bounded_answer(answer))


def _bounded_answer(answer: str) -> str:
    """Keep complete Markdown lines/tokens when enforcing the prose limit."""
    if len(answer) <= ANSWER_LIMIT:
        return answer
    limit = ANSWER_LIMIT - 3  # room for the visible truncation marker
    cutoff = answer.rfind("\n", 0, limit + 1)
    if cutoff <= 0:
        cutoff = max(0, answer.rfind(" ", 0, limit + 1))
    for match in PROTECTED_MARKDOWN.finditer(answer):
        if match.start() < cutoff < match.end():
            cutoff = match.start()
            break
    prefix = answer[:cutoff].rstrip()
    # A heading without its body is misleading, especially an empty Sources
    # section after its only link was excluded by the limit.
    prefix = re.sub(r"(?:^|\n)\s*#{1,6}\s+[^\n]+\s*$", "", prefix).rstrip()
    return prefix + "\n\n…" if prefix else "…"


def marker_position(text: str) -> int | None:
    match = MARKER_PATTERN.search(text)
    return match.start() if match is not None else None
