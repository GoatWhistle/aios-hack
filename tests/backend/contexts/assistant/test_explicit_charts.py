from __future__ import annotations

import pytest

from backend.contexts.assistant.application.orchestrator import Orchestrator, _contextual_tool_preset
from backend.contexts.assistant.application.tools import run_tool
from backend.contexts.assistant.application.tools.context import ConsoleContext, ToolContext
from backend.contexts.assistant.infrastructure.artifacts import ArtifactStore
from backend.contexts.assistant.infrastructure.knowledge import Knowledge
from backend.contexts.assistant.infrastructure.llm.fake_chat import FakeChatClient


@pytest.mark.parametrize('question', [
    'Раскрой полный журнал решений скважины 62 на шаге 0 в jarvis-policy-20260926.',
    'Почему именно скважина 62 была выбрана в прогоне jarvis-policy-20260926 на шаге 0?',
    'Show the decision journal for well 62 at step 0 in jarvis-policy-20260926.',
])
def test_explicit_journal_does_not_wait_for_model_to_retrieve_facts(question):
    assert _contextual_tool_preset(question, ConsoleContext(step=1, run_id='other-run')) == (
        ('decision_journal', {'well': '62', 'step': 0, 'run_id': 'jarvis-policy-20260926'}),
    )


@pytest.mark.parametrize('metric', ['закачки', 'жидкости', 'обводнённости'])
def test_named_run_preset_never_substitutes_a_different_requested_metric(metric):
    # Journal charts choose a metric by the recorded role. Before retrieval we
    # cannot know that it matches an explicitly requested metric.
    assert _contextual_tool_preset(
        f'Покажи график {metric} скважины 62 для run-a.', ConsoleContext()
    ) == ()


@pytest.mark.parametrize('question', [
    'Что такое журнал решений скважины 62?',
    'Не раскрывай журнал решений скважины 62.',
    'Покажи журнал решений скважин 62 и 63.',
    'Раскрой журнал решений скважины 62 на шагах 0–5.',
    'Раскрой журнал решений скважины 62 на шагах 0 и 1.',
    'Раскрой журнал решений скважины 62 на следующем шаге.',
    'Раскрой журнал решений скважины 62 последнего прогона.',
    'Покажи график скважины 62 последнего прогона.',
])
def test_journal_preset_does_not_guess_ambiguous_requests(question):
    assert _contextual_tool_preset(question, ConsoleContext(run_id='run-a')) == ()


@pytest.mark.parametrize('question, context, expected', [
    ('Покажи график скважины 62 для jarvis-policy-20260926.', ConsoleContext(step=0),
     (('decision_journal', {'well': '62', 'step': 0, 'run_id': 'jarvis-policy-20260926'}),)),
    ('А здесь какая скважина и шаг? Покажи график этой скважины и её измеренные связи.',
     ConsoleContext(selected_well='62', step=1),
     (('well_series', {'well': '62'}), ('connectivity', {'well': '62'}))),
    ('Show the injection chart for well 2.', ConsoleContext(selected_well='1'),
     (('well_series', {'well': '2', 'metric': 'injection_rate'}),)),
    ('Построй график обводнённости выбранной скважины.', ConsoleContext(selected_well='2'),
     (('well_series', {'well': '2', 'metric': 'watercut'}),)),
    ('Покажи график закачки скважины 2 на шагах 3–7.', ConsoleContext(),
     (('well_series', {'well': '2', 'metric': 'injection_rate', 'from_step': 3, 'to_step': 7}),)),
    ('Покажи график этой скважины.', ConsoleContext(selected_well='2', step=1, run_id='run-a'),
     (('decision_journal', {'well': '2', 'step': 1, 'run_id': 'run-a'}),)),
])
def test_explicit_chart_requests_resolve_data_before_model(question, context, expected):
    assert _contextual_tool_preset(question, context) == expected


@pytest.mark.parametrize('question', [
    'Что такое график скважины 2?',
    'Не показывай график скважины 2.',
    'Покажи, как работает построение графика скважины 2.',
    'Show me what a well chart means.',
    'Покажи графики скважин 1 и 2 для сравнения.',
    'Покажи график скважины.',
])
def test_chart_resolution_does_not_guess_ambiguous_or_negated_requests(question):
    assert _contextual_tool_preset(question, ConsoleContext()) == ()


def test_explicit_series_is_available_even_when_model_calls_no_tools(store: ArtifactStore):
    client = FakeChatClient(rounds=[], caption='Временной ряд показан в карточке.')
    events = list(Orchestrator(client=client, store=store, knowledge=Knowledge()).ask(
        'chart', 'Покажи график закачки скважины 1.', ConsoleContext(step=0)))
    cards = [event.body for event in events if event.type == 'card']
    assert cards and cards[0]['tool'] == 'well_series'
    assert cards[0]['card']['payload']['well'] == '1'
    assert cards[0]['card']['payload']['metric'] == 'injection_rate'
    assert len(cards[0]['card']['payload']['rows']) > 1
    assert any('Tool well_series returned' in (msg.content or '') for msg in client.calls[0][0])


def test_default_rate_series_uses_the_well_role(store: ArtifactStore):
    context = ToolContext(store=store, console=ConsoleContext(step=0))
    index = context.index()
    wells = index.require_step(0)['wells']
    for role, metric in [('INJ', 'injection_rate'), ('PROD', 'liquid_rate')]:
        well = str(next(row for row in wells if row['role'] == role)['well'])
        card = run_tool('well_series', context, {'well': well})
        assert card.payload['metric'] == metric
        assert card.payload['rows']

@pytest.mark.parametrize('question', [
    'Покажи график нефти скважины 2.',
    'Покажи график скважины 2 за 2012 год.',
    'Покажи график скважины 2 по последнему прогону.',
])
def test_chart_resolution_does_not_substitute_another_metric_period_or_source(question):
    assert _contextual_tool_preset(question, ConsoleContext(selected_well='2')) == ()


def test_model_repeating_a_completed_chart_does_not_duplicate_cards(store: ArtifactStore):
    from backend.contexts.assistant.infrastructure.llm.chat_events import ToolCall
    call = ToolCall(id='again', name='well_series', args={'well': '1', 'metric': 'injection_rate'})
    client = FakeChatClient(rounds=[[call], [call]], caption='Временной ряд показан в карточке.')
    events = list(Orchestrator(client=client, store=store, knowledge=Knowledge()).ask(
        'repeat-chart', 'Покажи график закачки скважины 1.', ConsoleContext(step=0)))
    cards = [event.body for event in events if event.type == 'card']
    assert len(cards) == 1
    assert cards[0]['card']['payload']['metric'] == 'injection_rate'
    assert sum(msg.role == 'tool' for msg in client.calls[-1][0]) == 2
