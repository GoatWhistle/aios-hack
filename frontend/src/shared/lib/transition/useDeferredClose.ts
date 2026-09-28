import { useEffect, useRef, useState } from 'react';
import { readDuration } from '@/shared/lib/transition/readDuration';

const CLOSE_TOKEN = '--duration-state';
const CLOSE_FALLBACK_MS = 160;

export const useDeferredClose = <T>(
  active: T | null
): { visible: T | null; closing: boolean } => {
  const [visible, setVisible] = useState<T | null>(active);
  const [closing, setClosing] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (timer.current !== null) {
      clearTimeout(timer.current);
      timer.current = null;
    }
    if (active !== null) {
      setVisible(active);
      setClosing(false);
      return;
    }
    if (visible === null) {
      return;
    }
    setClosing(true);
    timer.current = setTimeout(() => {
      setVisible(null);
      setClosing(false);
      timer.current = null;
    }, readDuration(CLOSE_TOKEN, CLOSE_FALLBACK_MS));
    return () => {
      if (timer.current !== null) {
        clearTimeout(timer.current);
        timer.current = null;
      }
    };
  }, [active, visible]);

  return { visible, closing };
};
