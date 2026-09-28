import { useLayoutEffect, useRef, type RefObject } from 'react';
import { readDuration } from '@/shared/lib/transition/readDuration';
import { readEasing } from '@/shared/lib/transition/readEasing';
import type { SlotRect } from '@/jarvis/sphere/lib/sphereSlot';

const FLIGHT_TOKEN = '--duration-sphere-flight';
const FLIGHT_FALLBACK_MS = 520;
const EASE_TOKEN = '--ease-emphasis';
const EASE_FALLBACK = 'ease-out';

const prefersReducedMotion = (): boolean =>
  typeof window !== 'undefined' &&
  typeof window.matchMedia === 'function' &&
  window.matchMedia('(prefers-reduced-motion: reduce)').matches;

export const flipFrom = (before: SlotRect, after: SlotRect): string => {
  const dx = before.left + before.width / 2 - (after.left + after.width / 2);
  const dy = before.top + before.height / 2 - (after.top + after.height / 2);
  const scale = after.width > 0 ? before.width / after.width : 1;
  return `translate(${dx.toFixed(2)}px, ${dy.toFixed(2)}px) scale(${scale.toFixed(4)})`;
};

export const usePoseFlip = <Pose>(
  node: RefObject<HTMLElement | null>,
  pose: Pose,
  active: boolean,
  shown: () => SlotRect | null,
  target: () => SlotRect | null,
  place: (slot: SlotRect) => void
): void => {
  const last = useRef(pose);

  useLayoutEffect(() => {
    if (last.current === pose) {
      return;
    }
    last.current = pose;
    if (!active) {
      return;
    }
    const before = shown();
    const after = target();
    if (after === null) {
      return;
    }
    place(after);
    const element = node.current;
    if (before === null || element === null || typeof element.animate !== 'function' || prefersReducedMotion()) {
      return;
    }
    element.getAnimations().forEach((running) => running.cancel());
    element.animate([{ transform: flipFrom(before, after) }, { transform: 'translate(0px, 0px) scale(1)' }], {
      duration: readDuration(FLIGHT_TOKEN, FLIGHT_FALLBACK_MS),
      easing: readEasing(EASE_TOKEN, EASE_FALLBACK)
    });
  }, [pose, active, node, shown, target, place]);
};
