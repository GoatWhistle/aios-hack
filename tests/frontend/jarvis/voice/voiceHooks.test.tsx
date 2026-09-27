import { act, renderHook, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { useRecorder } from '@/jarvis/voice/useRecorder';
import { I18nProvider } from '@/shared/i18n/I18nContext';
import { useSpeechInput } from '@/jarvis/voice/useSpeechInput';
import { useVoiceOutput } from '@/jarvis/voice/useVoiceOutput';

const mediaDescriptor = Object.getOwnPropertyDescriptor(navigator, 'mediaDevices');
const speechDescriptor = Object.getOwnPropertyDescriptor(window, 'SpeechRecognition');
const audioContextDescriptor = Object.getOwnPropertyDescriptor(window, 'AudioContext');

class FakeMediaRecorder {
  static isTypeSupported = vi.fn(() => false);
  static last: FakeMediaRecorder | null = null;
  state = 'inactive';
  mimeType = 'audio/webm';
  start = vi.fn(() => { this.state = 'recording'; });
  stop = vi.fn(() => { this.state = 'inactive'; });
  ondataavailable: ((event: { data: Blob }) => void) | null = null;
  onstop: (() => void) | null = null;
  constructor() { FakeMediaRecorder.last = this; }
}

class FakeRecognition {
  static last: FakeRecognition | null = null;
  static startError: DOMException | null = null;
  lang = '';
  continuous = false;
  interimResults = false;
  onresult: ((event: never) => void) | null = null;
  onend: (() => void) | null = null;
  onerror: ((event: { error?: string }) => void) | null = null;
  start = vi.fn(() => {
    if (FakeRecognition.startError !== null) throw FakeRecognition.startError;
  });
  stop = vi.fn();
  abort = vi.fn();
  constructor() { FakeRecognition.last = this; }
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  if (mediaDescriptor === undefined) {
    Reflect.deleteProperty(navigator, 'mediaDevices');
  } else {
    Object.defineProperty(navigator, 'mediaDevices', mediaDescriptor);
  }
  if (speechDescriptor === undefined) {
    Reflect.deleteProperty(window, 'SpeechRecognition');
  } else {
    Object.defineProperty(window, 'SpeechRecognition', speechDescriptor);
  }
  if (audioContextDescriptor === undefined) {
    Reflect.deleteProperty(window, 'AudioContext');
  } else {
    Object.defineProperty(window, 'AudioContext', audioContextDescriptor);
  }
  FakeMediaRecorder.last = null;
  FakeRecognition.last = null;
  FakeRecognition.startError = null;
});

describe('voice input recovery', () => {
  it('reports a microphone permission failure and clears recording state', async () => {
    vi.stubGlobal('MediaRecorder', FakeMediaRecorder);
    Object.defineProperty(navigator, 'mediaDevices', {
      configurable: true,
      value: { getUserMedia: vi.fn().mockRejectedValue(new DOMException('denied', 'NotAllowedError')) }
    });
    const onFailure = vi.fn();
    const { result } = renderHook(() => useRecorder({ lang: 'ru', onText: vi.fn(), onFailure }));

    act(() => result.current.start());
    await waitFor(() => expect(onFailure).toHaveBeenCalledWith('not-allowed'));
    expect(result.current.recording).toBe(false);
  });

  it('stops a late microphone grant when the user cancels while permission is pending', async () => {
    vi.stubGlobal('MediaRecorder', FakeMediaRecorder);
    let grant!: (stream: MediaStream) => void;
    Object.defineProperty(navigator, 'mediaDevices', {
      configurable: true,
      value: { getUserMedia: vi.fn(() => new Promise<MediaStream>((resolve) => { grant = resolve; })) }
    });
    const stopTrack = vi.fn();
    const stream = { getTracks: () => [{ stop: stopTrack }] } as unknown as MediaStream;
    const onFailure = vi.fn();
    const { result } = renderHook(() => useRecorder({ lang: 'ru', onText: vi.fn(), onFailure }));

    act(() => result.current.start());
    act(() => result.current.stop());
    await act(async () => { grant(stream); await Promise.resolve(); });

    expect(stopTrack).toHaveBeenCalledOnce();
    expect(FakeMediaRecorder.last).toBeNull();
    expect(onFailure).not.toHaveBeenCalled();
    expect(result.current.recording).toBe(false);
  });

  it('does not deliver one final browser transcript twice on recognition end', () => {
    Object.defineProperty(window, 'SpeechRecognition', { configurable: true, value: FakeRecognition });
    const onFinal = vi.fn();
    const onFailure = vi.fn();
    const wrapper = ({ children }: { children: React.ReactNode }) => <I18nProvider>{children}</I18nProvider>;
    const { result } = renderHook(() => useSpeechInput({ onFinal, onInterim: vi.fn(), onFailure }), { wrapper });

    act(() => result.current.start());
    const recognition = FakeRecognition.last;
    expect(recognition).not.toBeNull();
    act(() => recognition?.onresult?.({
      resultIndex: 0,
      results: [{ isFinal: true, 0: { transcript: 'Скважина 10' }, length: 1 }],
    } as never));
    act(() => recognition?.onend?.());

    expect(onFinal).toHaveBeenCalledTimes(1);
    expect(onFinal).toHaveBeenCalledWith('Скважина 10');
    expect(onFailure).not.toHaveBeenCalled();
  });

  it('clears listening state and reports a synchronous browser start denial', () => {
    FakeRecognition.startError = new DOMException('microphone denied', 'NotAllowedError');
    Object.defineProperty(window, 'SpeechRecognition', { configurable: true, value: FakeRecognition });
    const onFailure = vi.fn();
    const wrapper = ({ children }: { children: React.ReactNode }) => <I18nProvider>{children}</I18nProvider>;
    const { result } = renderHook(() => useSpeechInput({ onFinal: vi.fn(), onInterim: vi.fn(), onFailure }), { wrapper });

    act(() => result.current.start());

    expect(result.current.listening).toBe(false);
    expect(result.current.error).toBe('not-allowed');
    expect(onFailure).toHaveBeenCalledWith('not-allowed');
  });

  it('reports no-speech when browser recognition ends without a transcript', () => {
    Object.defineProperty(window, 'SpeechRecognition', { configurable: true, value: FakeRecognition });
    const onFailure = vi.fn();
    const onFinal = vi.fn();
    const wrapper = ({ children }: { children: React.ReactNode }) => <I18nProvider>{children}</I18nProvider>;
    const { result } = renderHook(() => useSpeechInput({ onFinal, onInterim: vi.fn(), onFailure }), { wrapper });

    act(() => result.current.start());
    act(() => FakeRecognition.last?.onerror?.({ error: 'no-speech' }));
    act(() => FakeRecognition.last?.onend?.());

    expect(result.current.listening).toBe(false);
    expect(result.current.error).toBe('no-speech');
    expect(onFailure).toHaveBeenCalledWith('no-speech');
    expect(onFinal).not.toHaveBeenCalled();
  });

  it('does not submit an interim transcript after network failure switches to server recording', () => {
    Object.defineProperty(window, 'SpeechRecognition', { configurable: true, value: FakeRecognition });
    const onFinal = vi.fn();
    const onFailure = vi.fn();
    const wrapper = ({ children }: { children: React.ReactNode }) => <I18nProvider>{children}</I18nProvider>;
    const { result } = renderHook(() => useSpeechInput({ onFinal, onInterim: vi.fn(), onFailure }), { wrapper });

    act(() => result.current.start());
    const recognition = FakeRecognition.last;
    act(() => recognition?.onresult?.({
      resultIndex: 0,
      results: [{ isFinal: false, 0: { transcript: 'Скважина 10' }, length: 1 }],
    } as never));
    act(() => recognition?.onerror?.({ error: 'network' }));
    act(() => recognition?.onend?.());

    expect(onFailure).toHaveBeenCalledWith('network');
    expect(onFinal).not.toHaveBeenCalled();
  });
});

describe('voice output interruption', () => {
  it('plays the server TTS audio for the read-answer action and clears state on end', async () => {
    const source = {
      connect: vi.fn(), start: vi.fn(), stop: vi.fn(), onended: null as (() => void) | null,
      buffer: null as AudioBuffer | null
    };
    const analyser = {
      fftSize: 512, connect: vi.fn(), getFloatTimeDomainData: vi.fn()
    };
    const context = {
      destination: {},
      decodeAudioData: vi.fn().mockResolvedValue({} as AudioBuffer),
      createBufferSource: vi.fn(() => source),
      createAnalyser: vi.fn(() => analyser)
    };
    Object.defineProperty(window, 'AudioContext', {
      configurable: true, value: vi.fn(() => context)
    });
    vi.stubGlobal('requestAnimationFrame', vi.fn(() => 1));
    vi.stubGlobal('cancelAnimationFrame', vi.fn());
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true, arrayBuffer: async () => new Uint8Array([1, 2, 3]).buffer
    });
    vi.stubGlobal('fetch', fetchMock);
    const { result } = renderHook(() => useVoiceOutput({
      enabled: false, lang: 'ru', ttsAvailable: true, text: null,
      answer: '# Ответ\n\nПроверка `серверной` озвучки.',
      onLevel: vi.fn(), onSpoken: vi.fn()
    }));

    act(() => result.current.readAll());
    await waitFor(() => expect(source.start).toHaveBeenCalledOnce());
    expect(fetchMock).toHaveBeenCalledWith('/api/jarvis/speak', expect.objectContaining({
      method: 'POST', body: JSON.stringify({ text: 'Ответ Проверка серверной озвучки.', lang: 'ru' })
    }));
    expect(context.decodeAudioData).toHaveBeenCalledOnce();
    expect(result.current.speaking).toBe(true);
    act(() => source.onended?.());
    expect(result.current.speaking).toBe(false);
  });

  it('does not start audio when playback is stopped during the server TTS request', async () => {
    let resolveFetch!: (response: Response) => void;
    let requestSignal: AbortSignal | undefined;
    vi.stubGlobal('fetch', vi.fn((_input: RequestInfo | URL, init?: RequestInit) => {
      requestSignal = init?.signal as AbortSignal | undefined;
      return new Promise<Response>((resolve) => { resolveFetch = resolve; });
    }));
    const AudioContextFake = vi.fn();
    Object.defineProperty(window, 'AudioContext', { configurable: true, value: AudioContextFake });
    const { result } = renderHook(() => useVoiceOutput({
      enabled: true,
      lang: 'ru',
      ttsAvailable: true,
      text: 'Проверка озвучки',
      answer: null,
      onLevel: vi.fn(),
      onSpoken: vi.fn()
    }));

    act(() => result.current.stop());
    expect(requestSignal?.aborted).toBe(true);
    await act(async () => {
      resolveFetch({ ok: true, arrayBuffer: async () => new ArrayBuffer(8) } as Response);
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(AudioContextFake).not.toHaveBeenCalled();
    expect(result.current.speaking).toBe(false);
  });
});
