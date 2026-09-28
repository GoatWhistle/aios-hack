import { useEffect, useState, type RefObject } from 'react';
import { fetchSessionEvents } from '@/jarvis/model/sessions';
import type { JarvisEvent } from '@/jarvis/transport/events';

const RESTORE_TIMEOUT_MS = 4000;

export const useSessionRestore = (
  current: RefObject<string>,
  generation: RefObject<number>,
  apply: (events: readonly JarvisEvent[]) => void
): boolean => {
  const [restored, setRestored] = useState(false);

  useEffect(() => {
    const id = current.current;
    const started = generation.current;
    const controller = new AbortController();
    let alive = true;
    const timer = window.setTimeout(() => controller.abort(), RESTORE_TIMEOUT_MS);
    const bounded: typeof fetch = (input, init) => fetch(input, { ...init, signal: controller.signal });
    void fetchSessionEvents(id, bounded)
      .then((events) => {
        if (!alive || controller.signal.aborted || events.length === 0) {
          return;
        }
        if (current.current !== id || generation.current !== started) {
          return;
        }
        apply(events);
      })
      .finally(() => {
        window.clearTimeout(timer);
        if (alive) {
          setRestored(true);
        }
      });
    return () => {
      alive = false;
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [current, generation, apply]);

  return restored;
};
