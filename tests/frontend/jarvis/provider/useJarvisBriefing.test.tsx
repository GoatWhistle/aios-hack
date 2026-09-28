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
    const options = { open: true, sessionId: 's1', sceneCount: 2, briefingStale: true, lang: 'ru', step: 0, pushEvents, mergeEvents, setLoading };
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
  it('does not replace a live question with a late initial briefing', async () => {
    let resolveStored!: (events: JarvisEvent[]) => void;
    mocks.fetchSessionEvents.mockImplementationOnce(() => new Promise<JarvisEvent[]>((resolve) => { resolveStored = resolve; }));
    const pushEvents = vi.fn();
    const mergeEvents = vi.fn();
    const setLoading = vi.fn();
    const options = { open: true, sessionId: 's1', briefingStale: false, lang: 'ru', scenario: 'base', step: 0, pushEvents, mergeEvents, setLoading };
    const { rerender } = renderHook(({ sceneCount }) => useJarvisBriefing({ ...options, sceneCount }), {
      initialProps: { sceneCount: 0 }
    });
    await waitFor(() => expect(mocks.fetchSessionEvents).toHaveBeenCalledTimes(1));
    rerender({ sceneCount: 1 });
    await act(async () => { resolveStored([summaryEvent('base')]); });
    expect(pushEvents).not.toHaveBeenCalled();
    expect(mergeEvents).not.toHaveBeenCalled();
    expect(mocks.fetchBriefing).not.toHaveBeenCalled();
    expect(setLoading).toHaveBeenLastCalledWith(false);
  });

  it('restarts an interrupted initial load after close/reopen and ignores its stale response', async () => {
    let resolveOld!: (events: JarvisEvent[]) => void;
    let resolveNew!: (events: JarvisEvent[]) => void;
    mocks.fetchSessionEvents
      .mockImplementationOnce(() => new Promise<JarvisEvent[]>((resolve) => { resolveOld = resolve; }))
      .mockImplementationOnce(() => new Promise<JarvisEvent[]>((resolve) => { resolveNew = resolve; }));
    const pushEvents = vi.fn();
    const mergeEvents = vi.fn();
    const setLoading = vi.fn();
    const options = { sessionId: 's1', sceneCount: 0, briefingStale: false, lang: 'ru', scenario: 'base', step: 0, pushEvents, mergeEvents, setLoading };
    const { rerender } = renderHook(({ open }) => useJarvisBriefing({ ...options, open }), { initialProps: { open: true } });
    rerender({ open: false });
    rerender({ open: true });
    expect(mocks.fetchSessionEvents).toHaveBeenCalledTimes(2);
    await act(async () => { resolveOld([summaryEvent('old')]); });
    expect(pushEvents).not.toHaveBeenCalled();
    expect(setLoading).toHaveBeenLastCalledWith(true);
    await act(async () => { resolveNew([summaryEvent('base')]); });
    expect(pushEvents).toHaveBeenCalledWith([summaryEvent('base')]);
    expect(setLoading).toHaveBeenLastCalledWith(false);
  });

  it('keeps a completed briefing cached across close/reopen', async () => {
    mocks.fetchBriefing.mockResolvedValue([summaryEvent('base')]);
    const options = { sessionId: 's1', sceneCount: 1, briefingStale: true, lang: 'ru', scenario: 'base', step: 0, pushEvents: vi.fn(), mergeEvents: vi.fn(), setLoading: vi.fn() };
    const { rerender } = renderHook(({ open }) => useJarvisBriefing({ ...options, open }), { initialProps: { open: true } });
    await waitFor(() => expect(options.setLoading).toHaveBeenLastCalledWith(false));
    rerender({ open: false });
    rerender({ open: true });
    expect(mocks.fetchBriefing).toHaveBeenCalledTimes(1);
  });

});
