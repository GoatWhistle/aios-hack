from backend.contexts.assistant.application.answer import ANSWER_LIMIT, split_answer


def test_answer_limit_does_not_cut_artifact_link_or_identifier() -> None:
    prefix = "Проверенные факты.\n" * 78
    url = "/api/jarvis/run-artifacts/jarvis-policy-20260926/manifest"
    answer = split_answer(f"Подпись\n---ОТВЕТ---\n{prefix}[Манифест]({url})\nЕщё факты.").answer
    assert answer is not None and len(answer) <= ANSWER_LIMIT
    assert "[Манифест](" not in answer or f"[Манифест]({url})" in answer


def test_answer_limit_does_not_leave_open_code_fence() -> None:
    prefix = "Проверенные факты.\n" * 78
    block = "```bash\n" + "python run.py\n" * 20 + "```"
    answer = split_answer(f"Подпись\n---ОТВЕТ---\n{prefix}{block}").answer
    assert answer is not None and len(answer) <= ANSWER_LIMIT
    assert answer.count("```") % 2 == 0


def test_answer_limit_does_not_leave_empty_heading() -> None:
    prefix = "Проверенные факты.\n" * 78
    answer = split_answer(f"Подпись\n---ОТВЕТ---\n{prefix}## Источники\n" + "x" * 500).answer
    assert answer is not None
    assert not answer.rstrip(". …\n").endswith("## Источники")
