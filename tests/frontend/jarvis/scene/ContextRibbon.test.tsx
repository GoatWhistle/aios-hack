import { render, screen, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { I18nProvider } from '@/shared/i18n/I18nContext';
import { JarvisSessionContext, JarvisVoiceContext } from '@/jarvis/provider/contexts';
import type { JarvisSessionValue } from '@/jarvis/model/jarvisValue';
import { ContextRibbon } from '@/jarvis/scene/ContextRibbon/ContextRibbon';

describe('context for the next Jarvis question', () => {
  it('shows the live well and step rather than the previously answered question', () => {
    const context = { scenario: 'base', step: 0, date: '2007-01-01', selected_well: '62', run_id: null };
    render(
      <I18nProvider>
        <JarvisSessionContext.Provider value={{
          askContext: { ...context, step: 1, date: '2007-02-01', selected_well: '10' },
          scenes: { activeIndex: 0, scenes: [{ context, answer: null }] },
          capabilities: { ok: true, tts: false, stt: 'none', docs: 0 }
        } as unknown as JarvisSessionValue}>
          <JarvisVoiceContext.Provider value={{
            speakEnabled: false, toggleSpeak: vi.fn(), confirmVoice: true, toggleConfirmVoice: vi.fn()
          } as never}>
            <ContextRibbon speaking={false} onStop={vi.fn()} onReadAll={vi.fn()}
              canRestorePrevious={false} onRestorePrevious={vi.fn()} />
          </JarvisVoiceContext.Provider>
        </JarvisSessionContext.Provider>
      </I18nProvider>
    );
    const facts = document.querySelector('.jarvis-ribbon-facts') as HTMLElement;
    expect(within(facts).getByText('10')).toBeTruthy();
    expect(within(facts).queryByText('62')).toBeNull();
    expect(screen.getByText(/Контекст консоли при вопросе/)).toBeTruthy();
    expect(facts.textContent).toContain('1');
    expect(facts.textContent).toContain('февраль');
  });
});
