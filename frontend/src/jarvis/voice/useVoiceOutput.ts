import { useCallback, useEffect, useRef, useState } from 'react';
import { rmsOf } from '@/jarvis/voice/useMicLevel';
import {
  fetchSpeech,
  pickVoice,
  plainSpeech,
  speakLang,
  speechSynthesisSupported
} from '@/jarvis/voice/speakText';

interface VoiceOptions {
  enabled: boolean;
  lang: string;
  ttsAvailable: boolean;
  text: string | null;
  answer: string | null;
  onLevel: (level: number) => void;
  onSpoken: () => void;
}

export interface VoiceOutput {
  speaking: boolean;
  stop: () => void;
  readAll: () => void;
}

const audioContextOf = (): AudioContext | null => {
  if (typeof window === 'undefined') {
    return null;
  }
  const scope = window as unknown as {
    AudioContext?: typeof AudioContext;
    webkitAudioContext?: typeof AudioContext;
  };
  const Constructor = scope.AudioContext ?? scope.webkitAudioContext ?? null;
  return Constructor === null ? null : new Constructor();
};

export const useVoiceOutput = ({
  enabled,
  lang,
  ttsAvailable,
  text,
  answer,
  onLevel,
  onSpoken
}: VoiceOptions): VoiceOutput => {
  const [speaking, setSpeaking] = useState(false);
  const level = useRef(onLevel);
  const spoken = useRef(onSpoken);
  const context = useRef<AudioContext | null>(null);
  const source = useRef<AudioBufferSourceNode | null>(null);
  const request = useRef<AbortController | null>(null);
  const raf = useRef(0);
  const generation = useRef(0);
  level.current = onLevel;
  spoken.current = onSpoken;

  const stop = useCallback(() => {
    generation.current += 1;
    request.current?.abort();
    request.current = null;
    cancelAnimationFrame(raf.current);
    raf.current = 0;
    try {
      source.current?.stop();
    } catch {
    }
    source.current = null;
    if (speechSynthesisSupported()) {
      window.speechSynthesis.cancel();
    }
    level.current(0);
    setSpeaking(false);
  }, []);

  const fallback = useCallback(
    (phrase: string, token: number) => {
      if (!speechSynthesisSupported() || generation.current !== token) {
        if (generation.current === token) {
          setSpeaking(false);
          level.current(0);
        }
        return;
      }
      const utterance = new SpeechSynthesisUtterance(phrase);
      utterance.lang = speakLang(lang);
      utterance.rate = 1;
      const voice = pickVoice(window.speechSynthesis.getVoices(), lang);
      if (voice !== null) {
        utterance.voice = voice;
      }
      utterance.onend = () => {
        if (generation.current !== token) return;
        setSpeaking(false);
        level.current(0);
      };
      window.speechSynthesis.cancel();
      window.speechSynthesis.speak(utterance);
      setSpeaking(true);
    },
    [lang]
  );

  const play = useCallback(
    async (phrase: string) => {
      const clean = plainSpeech(phrase);
      if (clean.length === 0) {
        return;
      }
      stop();
      const token = ++generation.current;
      setSpeaking(true);
      if (!ttsAvailable) {
        fallback(clean, token);
        return;
      }
      const requestController = new AbortController();
      request.current = requestController;
      const bytes = await fetchSpeech(clean, lang, requestController.signal);
      if (request.current === requestController) request.current = null;
      if (generation.current !== token) return;
      if (bytes === null || bytes.byteLength === 0) {
        fallback(clean, token);
        return;
      }
      const ctx = context.current ?? audioContextOf();
      if (ctx === null) {
        fallback(clean, token);
        return;
      }
      context.current = ctx;
      let buffer: AudioBuffer;
      try {
        buffer = await ctx.decodeAudioData(bytes.slice(0));
      } catch {
        fallback(clean, token);
        return;
      }
      if (generation.current !== token) return;
      const node = ctx.createBufferSource();
      node.buffer = buffer;
      const analyser = ctx.createAnalyser();
      analyser.fftSize = 512;
      node.connect(analyser);
      analyser.connect(ctx.destination);
      const samples = new Float32Array(analyser.fftSize);
      const tick = () => {
        analyser.getFloatTimeDomainData(samples);
        level.current(Math.min(1, rmsOf(samples) * 3.2));
        raf.current = requestAnimationFrame(tick);
      };
      node.onended = () => {
        if (generation.current !== token) return;
        cancelAnimationFrame(raf.current);
        raf.current = 0;
        level.current(0);
        setSpeaking(false);
        source.current = null;
      };
      source.current = node;
      setSpeaking(true);
      node.start();
      raf.current = requestAnimationFrame(tick);
    },
    [lang, ttsAvailable, stop, fallback]
  );

  useEffect(() => {
    if (!enabled || text === null || text.trim().length === 0) {
      return;
    }
    void play(text).then(() => spoken.current());
  }, [enabled, text, play]);

  useEffect(() => () => stop(), [stop]);

  const readAll = useCallback(() => {
    if (answer === null || answer.trim().length === 0) {
      return;
    }
    void play(answer);
  }, [answer, play]);

  return { speaking, stop, readAll };
};
