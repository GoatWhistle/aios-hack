import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { JarvisEvent } from '@/jarvis/transport/events';

const mocks = vi.hoisted(() => ({
  fetchBriefing: vi.fn(),
  fetchSessionEvents: vi.fn()
}));

vi.mock('@/jarvis/model/sessions', () => ({
  fetchBriefing: mocks.fetchBriefing,
  fetchSessionEvents: mocks.fetchSessionEvents,
  briefingMatchesContext: () => true
}));

import { useJarvisBriefing } from '@/jarvis/provider/useJarvisBriefing';

const summaryEvent = (scenario: string): JarvisEvent => ({
  type: 'scene', scene_id: 'briefing', question: '',
  context: { scenario, step: 0, date: '', selected_well: null, workspace: 'overview', view: 'fund' }
});

describe('useJarvisBriefing', () => {
  beforeEach(() => {
    mocks.fetchBriefing.mockReset();
    mocks.fetchSessionEvents.mockReset();
    mocks.fetchSessionEvents.mockResolvedValue([]);
  });

  it('drops an old summary response after a newer scenario request starts', async () => {
    let resolveBase!: (events: JarvisEvent[]) => void;
    let resolveCandidate!: (events: JarvisEvent[]) => void;
    mocks.fetchBriefing
      .mockImplementationOnce(() => new Promise<JarvisEvent[]>((resolve) => { resolveBase = resolve; }))
      .mockImplementationOnce(() => new Promise<JarvisEvent[]>((resolve) => { resolveCandidate = resolve; }));
    const pushEvents = vi.fn();
    const mergeEvents = vi.fn();
    const setLoading = vi.fn();
    const options = { open: true, sessionId: 's1', sceneCount: 2, hasBriefing: true, lang: 'ru', step: 0, pushEvents, mergeEvents, setLoading };
    const { rerender } = renderHook(({ scenario }) => useJarvisBriefing({ ...options, scenario }), {
      initialProps: { scenario: 'base' }
    });
    await waitFor(() => expect(mocks.fetchBriefing).toHaveBeenCalledTimes(1));
    rerender({ scenario: 'candidate' });
    await waitFor(() => expect(mocks.fetchBriefing).toHaveBeenCalledTimes(2));

    await act(async () => { resolveBase([summaryEvent('base')]); });
    expect(mergeEvents).not.toHaveBeenCalled();
    await act(async () => { resolveCandidate([summaryEvent('candidate')]); });
    expect(mergeEvents).toHaveBeenCalledWith([summaryEvent('candidate')]);
    expect(pushEvents).not.toHaveBeenCalled();
    expect(setLoading).toHaveBeenNthCalledWith(1, true);
    expect(setLoading).toHaveBeenLastCalledWith(false);
  });
});
