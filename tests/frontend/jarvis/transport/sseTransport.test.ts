import { describe, expect, it, vi } from 'vitest';
import { createSseTransport } from '@/jarvis/transport/sseTransport';
import type { JarvisAsk } from '@/jarvis/transport/JarvisTransport';
import type { JarvisEvent } from '@/jarvis/transport/events';

const ask: JarvisAsk = {
  sessionId: 'session-1',
  question: 'Почему?',
  lang: 'ru',
  context: {
    scenario: 'base',
    step: 96,
    date: '2015-01-01',
    selected_well: '10',
    workspace: 'field',
    view: 'projection'
  }
};

const responseWith = (body: string): Response => new Response(
  new ReadableStream<Uint8Array>({
    start(controller) {
      controller.enqueue(new TextEncoder().encode(body));
      controller.close();
    }
  }),
  { status: 200 }
);

const collect = async (
  events: AsyncIterable<JarvisEvent>
): Promise<JarvisEvent[]> => {
  const collected: JarvisEvent[] = [];
  for await (const event of events) collected.push(event);
  return collected;
};

describe('SSE answer completion', () => {
  it('reports a clean EOF without a terminal event as an incomplete stream', async () => {
    const fetchImpl = vi.fn().mockResolvedValue(responseWith(
      'data: {"type":"scene","scene_id":"s-1","question":"Почему?","context":{"scenario":"base","step":96,"date":"2015-01-01","selected_well":"10","workspace":"field","view":"projection"}}\n\n'
    ));
    const events = await collect(createSseTransport({ fetchImpl }).ask(ask, new AbortController().signal));

    expect(events.at(-1)).toEqual({
      type: 'error',
      code: 'incomplete-stream',
      message: 'the event stream ended before Jarvis completed the answer'
    });
  });

  it('dispatches a final event terminated by EOF and does not flag completion', async () => {
    const fetchImpl = vi.fn().mockResolvedValue(responseWith(
      'data: {"type":"done","scene_id":"s-1","tool_rounds":1,"elapsed_ms":25}'
    ));
    const events = await collect(createSseTransport({ fetchImpl }).ask(ask, new AbortController().signal));

    expect(events).toEqual([
      { type: 'done', scene_id: 's-1', tool_rounds: 1, elapsed_ms: 25 }
    ]);
  });

  it('reports an interrupted response body as an incomplete stream', async () => {
    let sent = false;
    const fetchImpl = vi.fn().mockResolvedValue(new Response(new ReadableStream<Uint8Array>({
      pull(controller) {
        if (sent) {
          controller.error(new Error('connection reset'));
          return;
        }
        sent = true;
        controller.enqueue(new TextEncoder().encode(
          'data: {"type":"scene","scene_id":"s-1","question":"Почему?","context":{"scenario":"base","step":96,"date":"2015-01-01","selected_well":"10","workspace":"field","view":"projection"}}\n\n'
        ));
      }
    }, { highWaterMark: 0 }), { status: 200 }));
    const events = await collect(createSseTransport({ fetchImpl }).ask(ask, new AbortController().signal));

    expect(events.map((event) => event.type)).toEqual(['scene', 'error']);
    expect(events.at(-1)).toEqual({
      type: 'error',
      code: 'incomplete-stream',
      message: 'the event stream ended before Jarvis completed the answer'
    });
  });

  it('cancels a pending SSE body read when the request is aborted', async () => {
    const controller = new AbortController();
    const bodyCancelled = vi.fn();
    const fetchImpl = vi.fn().mockResolvedValue(new Response(new ReadableStream<Uint8Array>({
      start() {},
      cancel: bodyCancelled
    }), { status: 200 }));
    const stream = createSseTransport({ fetchImpl }).ask(ask, controller.signal);
    const iterator = stream[Symbol.asyncIterator]();
    const pending = iterator.next();
    await Promise.resolve();

    controller.abort();

    await expect(pending).resolves.toEqual({ done: true, value: undefined });
    expect(bodyCancelled).toHaveBeenCalledTimes(1);
    expect(await iterator.next()).toEqual({ done: true, value: undefined });
  });

  it('treats an aborted fetch before response headers as cancellation', async () => {
    const controller = new AbortController();
    const fetchImpl = vi.fn((_input: RequestInfo | URL, init?: RequestInit) =>
      new Promise<Response>((_resolve, reject) => {
        init?.signal?.addEventListener('abort', () => {
          reject(new DOMException('The operation was aborted.', 'AbortError'));
        }, { once: true });
      })
    );
    const iterator = createSseTransport({ fetchImpl }).ask(ask, controller.signal)[Symbol.asyncIterator]();
    const pending = iterator.next();

    controller.abort();

    await expect(pending).resolves.toEqual({ done: true, value: undefined });
  });
});
