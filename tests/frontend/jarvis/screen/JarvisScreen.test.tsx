import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { Scene } from '@/jarvis/model/scenes';
import { JarvisScreen } from '@/jarvis/screen/JarvisScreen/JarvisScreen';
import { I18nProvider } from '@/shared/i18n/I18nContext';

const session = vi.hoisted(() => ({
  scenes: { scenes: [] as Scene[], activeIndex: 0, status: null, suggestions: [], tool: null },
  transition: { phase: 'open' },
  capabilities: {},
  selectScene: vi.fn(), close: vi.fn(), askQuestion: vi.fn(),
  applyAction: vi.fn(), showCompanion: vi.fn(), cancel: vi.fn()
}));
vi.mock('@/jarvis/provider/contexts', () => ({
  useJarvisSessionContext: () => session,
  useJarvisVoice: () => ({}),
  useJarvisSphere: () => ({ setAudioLevel: vi.fn() })
}));
vi.mock('@/jarvis/voice/useVoiceOutput', () => ({ useVoiceOutput: () => ({}) }));
vi.mock('@/jarvis/scene/ContextRibbon/ContextRibbon', () => ({ ContextRibbon: () => <input aria-label="Editable context" /> }));
vi.mock('@/jarvis/stage/JarvisDoor/JarvisDoor', () => ({ JarvisDoor: () => null }));
vi.mock('@/jarvis/scene/HistoryRail/HistoryRail', () => ({ HistoryRail: () => null }));
vi.mock('@/jarvis/scene/InputDock/InputDock', () => ({ InputDock: () => null }));
vi.mock('@/jarvis/voice/LiveTranscript/LiveTranscript', () => ({ LiveTranscript: () => null }));
vi.mock('@/jarvis/scene/WalkthroughControls/WalkthroughControls', () => ({ WalkthroughControls: () => null }));
vi.mock('@/jarvis/scene/SceneStatus/SceneStatus', () => ({ SceneStatus: () => null }));

describe('Jarvis workspace navigation', () => {
  beforeEach(() => { session.scenes.scenes = []; session.scenes.activeIndex = 0; });

  it('shows each newly selected answer from the top without jumping on streaming updates', () => {
    const first: Scene = {
      id: 'first', sourceId: 's1', question: 'Первый',
      context: { scenario: 'base', step: 0, date: '', selected_well: null, workspace: 'field', view: 'projection' },
      cards: [], captionDraft: '', caption: null, answerDraft: '', answer: null,
      ts: null, guarded: false, warnings: [], error: null, done: false
    };
    session.scenes.scenes = [first, { ...first, id: 'second', sourceId: 's2', question: 'Второй' }];
    const { container, rerender } = render(<I18nProvider><JarvisScreen /></I18nProvider>);
    const body = container.querySelector('.jarvis-screen-body') as HTMLElement;
    body.scrollTop = 1000;
    session.scenes.activeIndex = 1;
    rerender(<I18nProvider><JarvisScreen /></I18nProvider>);
    expect(body.scrollTop).toBe(0);
    body.scrollTop = 300;
    session.scenes.scenes[1] = { ...session.scenes.scenes[1], answerDraft: 'Пришла следующая часть ответа' };
    rerender(<I18nProvider><JarvisScreen /></I18nProvider>);
    expect(body.scrollTop).toBe(300);
  });

  it('scrolling the workspace or using arrow keys never silently changes the answer', () => {
    session.selectScene.mockClear();
    render(<I18nProvider><JarvisScreen /></I18nProvider>);
    fireEvent.wheel(screen.getByRole('dialog'), { deltaY: 120 });
    fireEvent.keyDown(screen.getByRole('dialog'), { key: 'ArrowDown' });
    expect(session.selectScene).not.toHaveBeenCalled();
  });

  it('does not steal slash from an editable context control', () => {
    render(<I18nProvider><JarvisScreen /></I18nProvider>);
    const event = new KeyboardEvent('keydown', { key: '/', bubbles: true, cancelable: true });
    screen.getByRole('textbox', { name: 'Editable context' }).dispatchEvent(event);
    expect(event.defaultPrevented).toBe(false);
  });
});
