import { describe, expect, it, vi } from 'vitest';
import { briefingMatchesContext, fetchBriefing } from '@/jarvis/model/sessions';
import type { JarvisEvent } from '@/jarvis/transport/events';

const briefing = (scenario: string, step: number): JarvisEvent => ({
  type: 'scene', scene_id: 'briefing', question: '',
  context: { scenario, step, date: '', selected_well: null, workspace: 'overview', view: 'fund' }
});

describe('briefing context in saved sessions', () => {
  it('keeps a summary that matches the selected scenario and step', () => {
    expect(briefingMatchesContext([briefing('base', 0)], 'base', 0)).toBe(true);
  });

  it('refreshes a saved summary for a changed scenario or step', () => {
    expect(briefingMatchesContext([briefing('base', 0)], 'candidate', 0)).toBe(false);
    expect(briefingMatchesContext([briefing('base', 0)], 'base', 4)).toBe(false);
  });

  it('does not invent a missing historical briefing', () => {
    expect(briefingMatchesContext([], 'base', 0)).toBe(true);
  });

  it('reports capacity rejection as retryable busy state', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ error: 'busy' }), { status: 429 })
    );
    const events = await fetchBriefing('s1', 'ru', 'base', 96, fetchMock);
    expect(events.at(-1)).toMatchObject({ type: 'error', code: 'busy' });
  });
});
