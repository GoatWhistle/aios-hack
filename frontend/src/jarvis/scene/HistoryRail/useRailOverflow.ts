import { useCallback, useEffect, useState, type RefObject } from 'react';

export interface RailOverflow {
  start: boolean;
  end: boolean;
  scrollBy: (direction: number) => void;
}

const EDGE = 2;
const STEP_RATIO = 0.8;

export const useRailOverflow = (
  ref: RefObject<HTMLElement | null>,
  count: number
): RailOverflow => {
  const [start, setStart] = useState(false);
  const [end, setEnd] = useState(false);

  const read = useCallback(() => {
    const node = ref.current;
    if (node === null) {
      return;
    }
    const maximum = node.scrollWidth - node.clientWidth;
    setStart(node.scrollLeft > EDGE);
    setEnd(maximum > EDGE && node.scrollLeft < maximum - EDGE);
  }, [ref]);

  useEffect(() => {
    const node = ref.current;
    if (node === null) {
      return;
    }
    read();
    node.addEventListener('scroll', read, { passive: true });
    const observer = new ResizeObserver(read);
    observer.observe(node);
    return () => {
      node.removeEventListener('scroll', read);
      observer.disconnect();
    };
  }, [ref, read, count]);

  const scrollBy = useCallback(
    (direction: number) => {
      const node = ref.current;
      if (node === null) {
        return;
      }
      const calm = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
      node.scrollBy({
        left: direction * node.clientWidth * STEP_RATIO,
        behavior: calm ? 'auto' : 'smooth'
      });
    },
    [ref]
  );

  return { start, end, scrollBy };
};
