import { describe, expect, it } from 'vitest';
import { MAX_ORBIT_CARDS, activeScene, emptyScenes, scenesReducer } from '@/jarvis/model/scenes';
import type { JarvisEvent } from '@/jarvis/transport/events';
import { card, opened, play } from '@support/scenesFixtures';

describe('a scene starts when the backend announces it', () => {
  it('records the question and context and makes it active', () => {
    const state = opened();
    expect(state.scenes.length).toBe(1);
    expect(state.activeIndex).toBe(0);
    expect(activeScene(state)?.question).toBe('почему');
    expect(activeScene(state)?.context.step).toBe(72);
  });

  it('replaces the singleton briefing when its scenario changes', () => {
    const briefing = (scenario: string): JarvisEvent => ({
      type: 'scene', scene_id: 'briefing', question: '',
      context: { scenario, step: 0, date: '2007-01-01', selected_well: null, workspace: 'overview', view: 'fund' }
    });
    const first = scenesReducer(emptyScenes, briefing('base'));
    const next = scenesReducer(first, briefing('candidate'));
    expect(next.scenes).toHaveLength(1);
    expect(activeScene(next)?.context.scenario).toBe('candidate');
  });

  it('refreshes an earlier briefing without changing the active user answer', () => {
    const briefing: JarvisEvent = {
      type: 'scene', scene_id: 'briefing', question: '',
      context: { scenario: 'base', step: 0, date: '2007-01-01', selected_well: null, workspace: 'overview', view: 'fund' }
    };
    const first = scenesReducer(emptyScenes, briefing);
    const user = scenesReducer(first, {
      type: 'scene', scene_id: 'ask-1', question: 'Почему так?',
      context: { scenario: 'base', step: 0, date: '2007-01-01', selected_well: null, workspace: 'overview', view: 'fund' }
    });
    const refresh = scenesReducer(user, {
      ...briefing,
      context: { ...briefing.context, scenario: 'candidate' }
    });
    expect(refresh.scenes).toHaveLength(2);
    expect(activeScene(refresh)?.question).toBe('Почему так?');
    expect(refresh.scenes[0].context.scenario).toBe('candidate');
  });

  it('puts the sphere into thinking the moment the scene opens', () => {
    expect(opened().status).toBe('thinking');
  });
});

describe('cards arrive in the order the backend reasoned', () => {
  it('sorts by order, not by arrival', () => {
    const state = play(
      [
        { type: 'card', scene_id: 's-01', card_id: 'c2', order: 2, card: card('второй') },
        { type: 'card', scene_id: 's-01', card_id: 'c1', order: 1, card: card('первый') }
      ],
      opened()
    );
    expect(activeScene(state)?.cards.map((entry) => entry.card.title)).toEqual([
      'первый',
      'второй'
    ]);
  });

  it('ignores a repeated card id instead of duplicating it', () => {
    const one: JarvisEvent = {
      type: 'card',
      scene_id: 's-01',
      card_id: 'c1',
      order: 1,
      card: card('раз')
    };
    const state = play([one, one], opened());
    expect(activeScene(state)?.cards.length).toBe(1);
  });

  it('never puts more than eight cards on the orbit', () => {
    const events: JarvisEvent[] = Array.from({ length: 9 }, (_, index) => ({
      type: 'card',
      scene_id: 's-01',
      card_id: `c${index}`,
      order: index,
      card: card(`карточка ${index}`)
    }));
    const state = play(events, opened());
    expect(activeScene(state)?.cards.length).toBe(MAX_ORBIT_CARDS);
  });

  it('drops a card addressed to a scene that does not exist', () => {
    const state = play(
      [{ type: 'card', scene_id: 'ghost', card_id: 'c1', order: 1, card: card('никто') }],
      opened()
    );
    expect(activeScene(state)?.cards.length).toBe(0);
  });
});

describe('the caption prints and is then replaced by the guarded version', () => {
  it('accumulates deltas', () => {
    const state = play(
      [
        { type: 'caption_delta', scene_id: 's-01', text: 'Скважину ' },
        { type: 'caption_delta', scene_id: 's-01', text: '51 закрыли' }
      ],
      opened()
    );
    expect(activeScene(state)?.captionDraft).toBe('Скважину 51 закрыли');
    expect(activeScene(state)?.caption).toBeNull();
  });

  it('replaces the draft wholesale when the guarded caption lands', () => {
    const state = play(
      [
        { type: 'caption_delta', scene_id: 's-01', text: 'выдумка 999 ' },
        { type: 'caption', scene_id: 's-01', text: 'без числа', guarded: true }
      ],
      opened()
    );
    expect(activeScene(state)?.caption).toBe('без числа');
    expect(activeScene(state)?.captionDraft).toBe('без числа');
    expect(activeScene(state)?.guarded).toBe(true);
  });
});

describe('warnings, suggestions, done and errors', () => {
  it('attaches a warning to the active scene', () => {
    const state = play(
      [{ type: 'warning', code: 'number-dropped', detail: 'вырезано 999' }],
      opened()
    );
    expect(activeScene(state)?.warnings).toEqual([
      { code: 'number-dropped', detail: 'вырезано 999' }
    ]);
  });

  it('ignores a warning arriving before any scene', () => {
    expect(play([{ type: 'warning', code: 'x', detail: '' }])).toBe(emptyScenes);
  });

  it('replaces the chips after each answer', () => {
    const state = play(
      [{ type: 'suggestions', items: [{ text: 'а' }, { text: 'б' }] }],
      opened()
    );
    expect(state.suggestions).toEqual(['а', 'б']);
  });

  it('marks the scene done and puts the sphere back to rest', () => {
    const state = play(
      [{ type: 'done', scene_id: 's-01', tool_rounds: 2, elapsed_ms: 100 }],
      opened()
    );
    expect(activeScene(state)?.done).toBe(true);
    expect(state.status).toBeNull();
  });

  it('records an error on the active scene and ends it', () => {
    const state = play(
      [{ type: 'error', code: 'timeout', message: 'долго' }],
      opened()
    );
    expect(activeScene(state)?.error).toEqual({ code: 'timeout', message: 'долго' });
    expect(activeScene(state)?.done).toBe(true);
    expect(state.status).toBeNull();
  });

  it('clears the status even when an error arrives with no scene open', () => {
    const state = play([{ type: 'error', code: 'no-api-key', message: 'нет ключа' }]);
    expect(state.status).toBeNull();
    expect(state.scenes).toEqual([]);
  });

  it('replays a late old-scene error without cancelling the newer answer or clearing its progress', () => {
    const first = opened();
    const next = scenesReducer(first, {
      type: 'scene', scene_id: 's-02', question: 'новый вопрос', context: first.scenes[0].context
    });
    const running = scenesReducer(next, { type: 'status', state: 'tool', tool: 'run_series' });
    const state = scenesReducer(running, { type: 'error', scene_id: 's-01', code: 'cancelled', message: 'old ask cancelled' });
    expect(state.scenes[0].error?.code).toBe('cancelled');
    expect(state.scenes[0].done).toBe(true);
    expect(activeScene(state)?.error).toBeNull();
    expect(activeScene(state)?.done).toBe(false);
    expect(state.status).toBe('tool');
    expect(state.tool).toBe('run_series');
    expect(scenesReducer(running, { type: 'error', scene_id: 'unknown', code: 'cancelled', message: '' })).toBe(running);
  });

  it('settles an identified current error even if the user is reading an older scene', () => {
    const first = opened();
    const next = scenesReducer(first, { type: 'scene', scene_id: 's-02', question: 'новый вопрос', context: first.scenes[0].context });
    const historical = { ...next, activeIndex: 0 };
    const state = scenesReducer(historical, { type: 'error', scene_id: 's-02', code: 'timeout', message: 'timeout' });
    expect(state.scenes[1].error?.code).toBe('timeout');
    expect(state.scenes[0].error).toBeNull();
    expect(state.status).toBeNull();
  });
});
