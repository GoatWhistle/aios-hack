import { useLayoutEffect, type RefObject } from 'react';

const INVITE_OFFSET = '--jarvis-invite-offset';

const layoutTop = (node: HTMLElement, root: HTMLElement): number => {
  let top = 0;
  let current: HTMLElement | null = node;
  while (current !== null && current !== root) {
    top += current.offsetTop;
    current = current.offsetParent as HTMLElement | null;
  }
  return top;
};

export const useInviteOffset = (
  rootRef: RefObject<HTMLElement | null>,
  sayRef: RefObject<HTMLElement | null>,
  active: boolean
): void => {
  useLayoutEffect(() => {
    const root = rootRef.current;
    const say = sayRef.current;
    if (root === null || say === null || !active) {
      return;
    }
    const measure = () => {
      root.style.setProperty(INVITE_OFFSET, `${layoutTop(say, root)}px`);
    };
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(root);
    return () => {
      observer.disconnect();
      root.style.removeProperty(INVITE_OFFSET);
    };
  }, [rootRef, sayRef, active]);
};
