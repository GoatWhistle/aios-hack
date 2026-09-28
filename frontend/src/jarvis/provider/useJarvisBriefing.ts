import { useEffect, useRef } from 'react';
import { briefingMatchesContext, fetchBriefing, fetchSessionEvents } from '@/jarvis/model/sessions';
import type { JarvisEvent } from '@/jarvis/transport/events';

interface BriefingOptions {
  open: boolean;
  sessionId: string;
  sceneCount: number;
  hasBriefing: boolean;
  lang: string;
  scenario: string;
  step: number;
  pushEvents: (events: readonly JarvisEvent[]) => void;
  mergeEvents: (events: readonly JarvisEvent[]) => void;
  setLoading: (loading: boolean) => void;
}

export const useJarvisBriefing = ({
  open,
  sessionId,
  sceneCount,
  hasBriefing,
  lang,
  scenario,
  step,
  pushEvents,
  mergeEvents,
  setLoading
}: BriefingOptions): void => {
  const requestedKey = useRef<string | null>(null);
  const pendingKey = useRef<string | null>(null);
  const requestSequence = useRef(0);

  useEffect(() => {
    if (!open || (sceneCount > 0 && !hasBriefing)) {
      // A question may start while initial session/briefing retrieval is pending.
      // Its late result must never pushEvents and abort that live request.
      requestSequence.current += 1;
      if (pendingKey.current !== null && requestedKey.current === pendingKey.current) {
        requestedKey.current = null;
      }
      pendingKey.current = null;
      setLoading(false);
      return;
    }
    const key = `${sessionId}|${lang}|${scenario}|${step}`;
    if (requestedKey.current === key) return;
    requestedKey.current = key;
    pendingKey.current = key;
    const requestId = ++requestSequence.current;
    setLoading(true);
    const start = async () => {
      if (sceneCount === 0) {
        const stored = await fetchSessionEvents(sessionId);
        if (requestId !== requestSequence.current) return;
        if (stored.length > 0) {
          pushEvents(stored);
          if (!briefingMatchesContext(stored, scenario, step)) {
            const refreshed = await fetchBriefing(sessionId, lang, scenario, step);
            if (requestId === requestSequence.current && refreshed.length > 0) mergeEvents(refreshed);
          }
          return;
        }
      }
      const events = await fetchBriefing(sessionId, lang, scenario, step);
      if (requestId !== requestSequence.current) return;
      if (events.length > 0) {
        if (sceneCount === 0) pushEvents(events);
        else mergeEvents(events);
      }
    };
    void start().finally(() => {
      if (requestId === requestSequence.current) {
        pendingKey.current = null;
        setLoading(false);
      }
    });
  }, [open, sessionId, sceneCount, hasBriefing, lang, scenario, step, pushEvents, mergeEvents, setLoading]);
};
