import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { MicButton } from '@/jarvis/voice/MicButton/MicButton';
import { I18nProvider } from '@/shared/i18n/I18nContext';

const speech = vi.hoisted(() => ({ supported: true, start: vi.fn(), stop: vi.fn(), noteLevel: vi.fn() }));
vi.mock('@/jarvis/provider/contexts', () => ({
  useJarvisSessionContext: () => ({ visible: true, capabilities: {} }),
  useJarvisVoice: () => ({ micOpen: false, setMicOpen: vi.fn(), setTranscript: vi.fn(), setSttError: vi.fn(), noteVoiceAsked: vi.fn() }),
  useJarvisSphere: () => ({ setAudioLevel: vi.fn() })
}));
vi.mock('@/jarvis/voice/useSpeechInput', () => ({ useSpeechInput: () => speech }));
vi.mock('@/jarvis/voice/useRecorder', () => ({ useRecorder: () => ({ supported: false }) }));
vi.mock('@/jarvis/voice/useMicLevel', () => ({ useMicLevel: () => {} }));

describe('microphone shortcut ownership', () => {
  beforeEach(() => { speech.start.mockClear(); });
  it('preserves Space activation of settings, buttons, and links', () => {
    render(<I18nProvider><details><summary>Settings</summary></details><button>Action</button><a href="#test">Link</a><MicButton onTranscript={vi.fn()} onCommit={vi.fn()} /></I18nProvider>);
    for (const target of [screen.getByText('Settings'), screen.getByText('Action'), screen.getByText('Link')]) {
      const event = new KeyboardEvent('keydown', { key: ' ', code: 'Space', bubbles: true, cancelable: true });
      target.dispatchEvent(event);
      expect(event.defaultPrevented).toBe(false);
    }
    expect(speech.start).not.toHaveBeenCalled();
  });

  it('leaves modified shortcuts to the browser and retains plain M', () => {
    render(<I18nProvider><div data-testid="stage" /><MicButton onTranscript={vi.fn()} onCommit={vi.fn()} /></I18nProvider>);
    const target = screen.getByTestId('stage');
    for (const modifier of ['ctrlKey', 'metaKey', 'altKey']) {
      const event = new KeyboardEvent('keydown', { key: 'm', [modifier]: true, bubbles: true, cancelable: true });
      target.dispatchEvent(event);
      expect(event.defaultPrevented).toBe(false);
    }
    expect(speech.start).not.toHaveBeenCalled();
    fireEvent.keyDown(target, { key: 'm' });
    expect(speech.start).toHaveBeenCalledOnce();
  });
});
