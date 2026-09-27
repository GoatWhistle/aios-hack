from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping, Sequence

from backend.contexts.assistant.application.answer import ANSWER_MARKER
from backend.contexts.assistant.infrastructure.system_map import SystemMap
from backend.contexts.assistant.domain.console_context import ConsoleContext
from backend.shared.json_io import read_json

PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"
PROMPT_FILE = "prompt.json"
PROMPT_LANG = "ru"
DEFAULT_LANG = "ru"
MAX_CAPTION_SENTENCES = 2
ANSWER_LIMIT = 1500
BRIEF_NODES: tuple[str, ...] = (
    "console",
    "jarvis",
    "search",
    "surrogate",
    "policy",
    "opm",
    "runs",
)


class PromptResources:
    def __init__(self, lang: str = PROMPT_LANG) -> None:
        payload = read_json(PROMPTS_DIR / lang / PROMPT_FILE)
        if not isinstance(payload, dict):
            raise TypeError(f"prompt resource {lang}: an object is expected")
        self._payload: Mapping[str, Any] = payload

    def lines(self, key: str) -> tuple[str, ...]:
        return tuple(str(item) for item in self._payload[key])

    def section(self, key: str) -> str:
        return str(self._payload["sections"][key])

    def context_label(self, key: str) -> str:
        return str(self._payload["context_labels"][key])

    def live_label(self, key: str) -> str:
        return str(self._payload["live_labels"][key])

    def language_name(self, lang: str) -> str:
        names = self._payload["language_names"]
        return str(names.get(lang, names[DEFAULT_LANG]))


@lru_cache(maxsize=2)
def prompt_resources(lang: str = PROMPT_LANG) -> PromptResources:
    resource_lang = lang if lang in {"ru", "en"} else PROMPT_LANG
    return PromptResources(resource_lang)


PROMPT_TEXT = prompt_resources()


def format_rules(
    lang: str, resources: PromptResources | None = None
) -> tuple[str, ...]:
    resources = resources or prompt_resources(lang)
    return tuple(
        template.format(
            max_caption_sentences=MAX_CAPTION_SENTENCES,
            answer_marker=ANSWER_MARKER,
            answer_limit=ANSWER_LIMIT,
        )
        for template in resources.lines("format_rules")
    )


def context_lines(
    console: ConsoleContext, resources: PromptResources | None = None
) -> list[str]:
    resources = resources or prompt_resources(console.lang)
    lines = [resources.context_label("scenario").format(value=console.scenario)]
    if console.step is not None:
        lines.append(resources.context_label("step").format(value=console.step))
    if console.date is not None:
        lines.append(resources.context_label("date").format(value=console.date))
    if console.selected_well is not None:
        lines.append(
            resources.context_label("selected_well").format(
                value=console.selected_well
            )
        )
    if console.run_id is not None:
        lines.append(resources.context_label("run_id").format(value=console.run_id))
    if console.context_version is not None:
        lines.append(resources.context_label("context_version").format(value=console.context_version))
    if console.workspace is not None and console.view is not None:
        lines.append(
            resources.context_label("screen").format(
                workspace=console.workspace, view=console.view
            )
        )
    return lines


def live_lines(
    live: Mapping[str, Any] | None, resources: PromptResources | None = None
) -> list[str]:
    resources = resources or PROMPT_TEXT
    if not live:
        return []
    lines: list[str] = []
    champion = live.get("champion")
    if isinstance(champion, Mapping) and champion.get("recorded"):
        lines.append(
            resources.live_label("champion").format(
                schedule_hash=str(champion.get("schedule_hash"))[:12],
                npv=champion.get("opm_npv_rub"),
                sound=champion.get("sound"),
            )
        )
    last = live.get("last_run")
    if isinstance(last, Mapping) and last.get("recorded"):
        lines.append(
            resources.live_label("last_run").format(
                run_id=last.get("run_id"),
                status=last.get("status"),
                verified_npv=last.get("verified_npv"),
            )
        )
    elif isinstance(last, Mapping) and last.get("reason"):
        lines.append(resources.live_label("no_runs").format(reason=last["reason"]))
    alerts = live.get("alerts")
    if isinstance(alerts, Sequence) and alerts:
        item = resources.live_label("alert_item")
        listed = ", ".join(
            item.format(
                name=row.get("name"), well=row.get("well"), step=row.get("step")
            )
            for row in alerts
            if isinstance(row, Mapping)
        )
        lines.append(resources.live_label("alerts").format(listed=listed))
    return lines


def about_lines(
    system: SystemMap | None, lang: str, resources: PromptResources | None = None
) -> list[str]:
    resources = resources or prompt_resources(lang)
    fallback = list(resources.lines("fallback_about"))
    if system is None:
        return fallback
    lines = system.brief(lang, BRIEF_NODES)
    return lines if lines else fallback


def build_system_prompt(
    console: ConsoleContext,
    lang: str = DEFAULT_LANG,
    system: SystemMap | None = None,
    live: Mapping[str, Any] | None = None,
    memory: str = "",
) -> str:
    resources = prompt_resources(lang)
    language = resources.language_name(lang)
    parts: list[str] = list(resources.lines("role"))
    parts.append(resources.section("about"))
    parts.extend(f"- {line}" for line in about_lines(system, lang, resources))
    parts.append(resources.section("console_context"))
    parts.extend(context_lines(console, resources))
    live_block = live_lines(live, resources)
    if live_block:
        parts.append(resources.section("live_state"))
        parts.extend(live_block)
    parts.append(resources.section("defaults_notice"))
    parts.append(resources.section("playbook"))
    parts.extend(f"- {line}" for line in resources.lines("playbook"))
    parts.append(resources.section("format"))
    parts.extend(f"- {line}" for line in format_rules(lang, resources))
    parts.append(resources.section("rules"))
    parts.extend(f"- {line}" for line in resources.lines("rules"))
    if memory:
        parts.append(resources.section("memory"))
        parts.append(memory)
    parts.append(resources.section("language_line").format(language=language))
    return "\n".join(parts)
