import { act, renderHook, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { useJarvisSession } from '@/jarvis/provider/useJarvisSession';
import type { JarvisTransport } from '@/jarvis/transport/JarvisTransport';
import type { JarvisEvent, JarvisAskContext } from '@/jarvis/transport/events';
import { createSseTransport } from '@/jarvis/transport/sseTransport';

const context: JarvisAskContext = {
  scenario: 'base', step: 0, date: '2007-01-01', selected_well: null,
  workspace: 'overview', view: 'fund'
};

describe('briefing refresh event merge', () => {
  afterEach(() => vi.unstubAllGlobals());

  it('restores an unterminated snapshot as interrupted while preserving evidence and allowing a new ask', async () => {
    const calls: string[] = [];
    const transport: JarvisTransport = {
      mode: 'sse',
      ask: (request) => ({ async *[Symbol.asyncIterator]() {
        calls.push(request.question);
        yield { type: 'scene', scene_id: 'next', question: request.question, context } as JarvisEvent;
        yield { type: 'done', scene_id: 'next', elapsed_ms: 1, tool_rounds: 0 } as JarvisEvent;
      } })
    };
    const { result } = renderHook(() => useJarvisSession(transport, 'ru', context));
    act(() => result.current.pushEvents([
      { type: 'scene', scene_id: 'complete', question: 'completed', context },
      { type: 'done', scene_id: 'complete', elapsed_ms: 1, tool_rounds: 0 },
      { type: 'scene', scene_id: 'legacy', question: 'legacy unfinished', context },
      { type: 'card', scene_id: 'legacy', card_id: 'c1', order: 0, card: { type: 'metric', title: 'Данные', payload: {}, provenance: 'recorded' } },
      { type: 'answer_delta', scene_id: 'legacy', text: 'Незавершённый текст' }
    ]));
    expect(result.current.busy).toBe(false);
    expect(result.current.scenes.status).toBeNull();
    expect(result.current.scenes.tool).toBeNull();
    const restored = result.current.scenes.scenes[1];
    expect(restored.done).toBe(true);
    expect(restored.error?.code).toBe('interrupted');
    expect(restored.cards[0].card.title).toBe('Данные');
    expect(restored.answerDraft).toBe('Незавершённый текст');
    expect(result.current.scenes.scenes[0].error).toBeNull();
    act(() => result.current.askQuestion('Продолжим?'));
    await waitFor(() => expect(calls).toEqual(['Продолжим?']));
    await waitFor(() => expect(result.current.busy).toBe(false));
  });

  it.each(['event', 'throw'])('attributes a live %s failure to its request while an older scene is selected', async (failure) => {
    let fail!: () => void;
    const waiting = new Promise<void>((resolve) => { fail = resolve; });
    const transport: JarvisTransport = {
      mode: 'sse',
      ask: () => ({ async *[Symbol.asyncIterator]() {
        yield { type: 'scene', scene_id: 'live', question: 'live', context } as JarvisEvent;
        await waiting;
        if (failure === 'throw') throw new Error('transport failed');
        yield { type: 'error', code: 'upstream', message: 'legacy provider error' } as JarvisEvent;
      } })
    };
    const { result } = renderHook(() => useJarvisSession(transport, 'ru', context));
    act(() => result.current.pushEvents([
      { type: 'scene', scene_id: 'archived', question: 'archived', context },
      { type: 'done', scene_id: 'archived', elapsed_ms: 1, tool_rounds: 0 }
    ]));
    act(() => result.current.askQuestion('live'));
    await waitFor(() => expect(result.current.scenes.scenes.at(-1)?.sourceId).toBe('live'));
    act(() => result.current.selectScene(0));
    await act(async () => { fail(); });
    await waitFor(() => expect(result.current.busy).toBe(false));
    expect(result.current.scenes.scenes[0].error).toBeNull();
    expect(result.current.scenes.scenes[1].error?.code).toBe('upstream');
    expect(result.current.scenes.scenes[1].done).toBe(true);
    expect(result.current.scenes.status).toBeNull();
  });

  it('releases live progress on request failure after a briefing was appended during the ask', async () => {
    let fail!: () => void;
    const waiting = new Promise<void>((resolve) => { fail = resolve; });
    const transport: JarvisTransport = {
      mode: 'sse',
      ask: () => ({ async *[Symbol.asyncIterator]() {
        yield { type: 'scene', scene_id: 'live', question: 'live', context } as JarvisEvent;
        await waiting;
        yield { type: 'error', code: 'upstream', message: 'provider failed' } as JarvisEvent;
      } })
    };
    const { result } = renderHook(() => useJarvisSession(transport, 'ru', context));
    act(() => result.current.askQuestion('live'));
    await waitFor(() => expect(result.current.scenes.scenes.at(-1)?.sourceId).toBe('live'));
    act(() => result.current.mergeEvents([
      { type: 'scene', scene_id: 'briefing', question: '', context },
      { type: 'done', scene_id: 'briefing', elapsed_ms: 1, tool_rounds: 0 }
    ]));
    expect(result.current.scenes.scenes.at(-1)?.sourceId).toBe('briefing');
    expect(result.current.busy).toBe(true);
    await act(async () => { fail(); });
    await waitFor(() => expect(result.current.busy).toBe(false));
    expect(result.current.scenes.scenes[0].error?.code).toBe('upstream');
    expect(result.current.scenes.status).toBeNull();
    expect(result.current.scenes.tool).toBeNull();
  });

  it('does not cancel or replace an active user answer', async () => {
    const requestSignals: AbortSignal[] = [];
    const transport: JarvisTransport = {
      mode: 'sse',
      ask: (_ask, signal) => {
        requestSignals.push(signal);
        return {
          async *[Symbol.asyncIterator]() {
            yield { type: 'scene', scene_id: 'answer-1', question: 'Почему?', context } as JarvisEvent;
            await new Promise<void>((resolve) => signal.addEventListener('abort', () => resolve(), { once: true }));
          }
        };
      }
    };
    const { result } = renderHook(() => useJarvisSession(transport, 'ru', context));
    act(() => result.current.askQuestion('Почему?'));
    await waitFor(() => expect(result.current.scenes.scenes.some((scene) => scene.sourceId === 'answer-1')).toBe(true));
    const briefing: JarvisEvent = {
      type: 'scene', scene_id: 'briefing', question: '',
      context: { ...context, scenario: 'candidate' }
    };

    act(() => result.current.mergeEvents([briefing]));

    expect(requestSignals[0]?.aborted).toBe(false);
    expect(result.current.busy).toBe(true);
    expect(result.current.scenes.scenes).toHaveLength(2);
    expect(result.current.scenes.scenes[result.current.scenes.activeIndex].sourceId).toBe('answer-1');
    act(() => result.current.cancel());
  });

  it('does not replace the current console context when an old scene is selected', async () => {
    const currentContext: JarvisAskContext = {
      ...context,
      scenario: 'base',
      step: 96,
      date: '2015-01-01',
      selected_well: '1'
    };
    const historicalContext: JarvisAskContext = {
      ...context,
      scenario: 'candidate',
      run_id: 'old-run',
      step: 10,
      date: '2007-11-01',
      selected_well: '13'
    };
    const calls: { context: JarvisAskContext }[] = [];
    const transport: JarvisTransport = {
      mode: 'sse',
      ask: (request) => {
        calls.push({ context: request.context });
        return {
          async *[Symbol.asyncIterator]() {
            yield {
              type: 'scene', scene_id: 'new-question', question: 'Сейчас?', context: request.context
            } as JarvisEvent;
            yield { type: 'done', scene_id: 'new-question', elapsed_ms: 1, tool_rounds: 0 } as JarvisEvent;
          }
        };
      }
    };
    const { result } = renderHook(() => useJarvisSession(transport, 'ru', currentContext));
    act(() => result.current.pushEvents([
      { type: 'scene', scene_id: 'old-answer', question: 'Тогда?', context: historicalContext },
      { type: 'caption', scene_id: 'old-answer', text: 'Старый ответ.', guarded: true },
      { type: 'done', scene_id: 'old-answer', elapsed_ms: 1, tool_rounds: 0 }
    ]));

    act(() => result.current.selectScene(0));
    expect(result.current.scenes.scenes[result.current.scenes.activeIndex]?.context).toEqual(historicalContext);
    act(() => result.current.askQuestion('Что сейчас?'));
    await waitFor(() => expect(calls).toHaveLength(1));

    expect(calls[0]?.context).toEqual(currentContext);
  });

  it('aborts an active request when the selected context changes', async () => {
    const signals: AbortSignal[] = [];
    const transport: JarvisTransport = {
      mode: 'sse',
      ask: (request, signal) => {
        signals.push(signal);
        return {
          async *[Symbol.asyncIterator]() {
            yield {
              type: 'scene', scene_id: 'old-context', question: request.question, context: request.context
            } as JarvisEvent;
            await new Promise<void>((resolve) => signal.addEventListener('abort', () => resolve(), { once: true }));
            yield { type: 'caption', scene_id: 'old-context', text: 'Late answer.', guarded: true } as JarvisEvent;
          }
        };
      }
    };
    const firstContext = { ...context, context_version: 'well-1-step-96', selected_well: '1', step: 96 };
    const { result, rerender } = renderHook(
      ({ askContext }) => useJarvisSession(transport, 'ru', askContext),
      { initialProps: { askContext: firstContext } }
    );

    act(() => result.current.askQuestion('Что здесь?'));
    await waitFor(() => expect(result.current.scenes.scenes.some((scene) => scene.sourceId === 'old-context')).toBe(true));
    rerender({ askContext: { ...firstContext, context_version: 'well-2-step-96', selected_well: '2' } });

    await waitFor(() => expect(signals[0]?.aborted).toBe(true));
    await waitFor(() => expect(result.current.busy).toBe(false));
    const cancelled = result.current.scenes.scenes.find((scene) => scene.sourceId === 'old-context');
    expect(cancelled?.caption).toBeNull();
    expect(cancelled?.done).toBe(true);
    expect(cancelled?.error?.code).toBe('cancelled');
    expect(result.current.scenes.status).toBeNull();
  });

  it('surfaces an API outage on the active scene and releases the busy state', async () => {
    const transport = createSseTransport({
      fetchImpl: vi.fn().mockRejectedValue(new TypeError('network unavailable'))
    });
    const { result } = renderHook(() => useJarvisSession(transport, 'ru', context));

    act(() => result.current.askQuestion('Почему скважина остановилась?'));

    await waitFor(() => {
      expect(result.current.busy).toBe(false);
      expect(result.current.scenes.scenes.at(-1)?.error).toEqual({
        code: 'upstream',
        message: 'jarvis service is unreachable'
      });
    });
  });

  it('sends an immediate request to the session selected for restoration', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ events: [] }), { status: 200 })
    ));
    const requests: { sessionId: string }[] = [];
    const transport: JarvisTransport = {
      mode: 'sse',
      ask: (request) => {
        requests.push({ sessionId: request.sessionId });
        return {
          async *[Symbol.asyncIterator]() {
            yield {
              type: 'scene', scene_id: 'restored-follow-up', question: request.question, context: request.context
            } as JarvisEvent;
            yield { type: 'done', scene_id: 'restored-follow-up', elapsed_ms: 1, tool_rounds: 0 } as JarvisEvent;
          }
        };
      }
    };
    const { result } = renderHook(() => useJarvisSession(transport, 'ru', context));

    act(() => {
      result.current.loadSession('restored-session');
      result.current.askQuestion('Продолжим?');
    });
    await waitFor(() => expect(requests).toHaveLength(1));

    expect(requests[0]?.sessionId).toBe('restored-session');
  });

  it('discards a late event from a request replaced by a follow-up', async () => {
    const signals: AbortSignal[] = [];
    const transport: JarvisTransport = {
      mode: 'sse',
      ask: (request, signal) => {
        signals.push(signal);
        return {
          async *[Symbol.asyncIterator]() {
            const id = request.question === 'first' ? 'first-scene' : 'second-scene';
            yield { type: 'scene', scene_id: id, question: request.question, context } as JarvisEvent;
            if (request.question === 'first') {
              await new Promise<void>((resolve) => signal.addEventListener('abort', () => resolve(), { once: true }));
              yield { type: 'status', scene_id: id, state: 'thinking', tool: 'stale-tool' } as JarvisEvent;
              return;
            }
            yield { type: 'done', scene_id: id, elapsed_ms: 1, tool_rounds: 0 } as JarvisEvent;
          }
        };
      }
    };
    const { result } = renderHook(() => useJarvisSession(transport, 'ru', context));

    act(() => result.current.pushEvents([
      { type: 'scene', scene_id: 'archived-scene', question: 'archived', context } as JarvisEvent,
      { type: 'done', scene_id: 'archived-scene', elapsed_ms: 1, tool_rounds: 0 } as JarvisEvent
    ]));
    act(() => result.current.askQuestion('first'));
    await waitFor(() => expect(result.current.scenes.scenes.some((scene) => scene.sourceId === 'first-scene')).toBe(true));
    act(() => result.current.selectScene(0));
    act(() => result.current.askQuestion('second'));

    await waitFor(() => expect(result.current.scenes.scenes.some((scene) => scene.sourceId === 'second-scene' && scene.done)).toBe(true));
    expect(signals[0]?.aborted).toBe(true);
    expect(result.current.scenes.status).toBeNull();
    expect(result.current.scenes.tool).toBeNull();
    expect(result.current.scenes.scenes.find((scene) => scene.sourceId === 'first-scene')?.error?.code).toBe('cancelled');
    expect(result.current.scenes.scenes.find((scene) => scene.sourceId === 'archived-scene')?.error).toBeNull();
  });

  it('ignores a stale restoration response when the same session is loaded twice', async () => {
    let resolveFirst!: (response: Response) => void;
    const staleResponse = new Promise<Response>((resolve) => { resolveFirst = resolve; });
    const events = (id: string) => ({ events: [
      { type: 'scene', scene_id: id, question: id, context }
    ] });
    const fetchImpl = vi.fn()
      .mockImplementationOnce(() => staleResponse)
      .mockResolvedValueOnce(new Response(JSON.stringify(events('latest-restoration')), { status: 200 }));
    vi.stubGlobal('fetch', fetchImpl);
    const transport: JarvisTransport = {
      mode: 'sse',
      ask: () => ({ async *[Symbol.asyncIterator]() {} })
    };
    const { result } = renderHook(() => useJarvisSession(transport, 'ru', context));

    act(() => result.current.loadSession('same-session'));
    act(() => result.current.loadSession('same-session'));
    await waitFor(() => expect(result.current.scenes.scenes.at(-1)?.sourceId).toBe('latest-restoration'));

    const staleJson = vi.fn().mockResolvedValue(events('stale-restoration'));
    const response = new Response(null, { status: 200 });
    Object.defineProperty(response, 'json', { value: staleJson });
    resolveFirst(response);
    await waitFor(() => expect(staleJson).toHaveBeenCalledTimes(1));
    expect(result.current.scenes.scenes.map((scene) => scene.sourceId)).toEqual(['latest-restoration']);
  });

  it('does not restore old history after starting a new conversation', async () => {
    let resolveHistory!: (response: Response) => void;
    const history = new Promise<Response>((resolve) => { resolveHistory = resolve; });
    const fetchImpl = vi.fn().mockReturnValue(history);
    vi.stubGlobal('fetch', fetchImpl);
    const transport: JarvisTransport = {
      mode: 'sse',
      ask: () => ({ async *[Symbol.asyncIterator]() {} })
    };
    const { result } = renderHook(() => useJarvisSession(transport, 'ru', context));

    act(() => result.current.loadSession('old-session'));
    act(() => result.current.startSession());
    const newSessionId = result.current.sessionId;
    const staleJson = vi.fn().mockResolvedValue({ events: [
      { type: 'scene', scene_id: 'old-history', question: 'old', context }
    ] });
    const response = new Response(null, { status: 200 });
    Object.defineProperty(response, 'json', { value: staleJson });
    resolveHistory(response);

    await waitFor(() => expect(staleJson).toHaveBeenCalledTimes(1));
    expect(result.current.sessionId).toBe(newSessionId);
    expect(result.current.scenes.scenes).toEqual([]);
  });
});
