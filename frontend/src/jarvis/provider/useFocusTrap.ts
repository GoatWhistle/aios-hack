import { useEffect, type RefObject } from 'react';

const FOCUSABLE = [
  'a[href]',
  'button:not([disabled])',
  'input:not([disabled])',
  'textarea:not([disabled])',
  'select:not([disabled])',
  'summary',
  '[tabindex]:not([tabindex="-1"])'
].join(',');

export const focusableWithin = (root: Element | null): HTMLElement[] => {
  if (root === null) {
    return [];
  }
  return [...root.querySelectorAll<HTMLElement>(FOCUSABLE)].filter((node) => {
    if (node.closest('[hidden], [inert], [aria-hidden="true"]') !== null) return false;
    if (node.getAttribute('tabindex') === '-1') return false;
    if (node.tagName !== 'SUMMARY' && node.tabIndex === -1) return false;
    if (node.offsetParent === null && getComputedStyle(node).position !== 'fixed') return false;
    const box = node.getClientRects();
    if (box.length === 0) return false;
    let ancestor: Element | null = node;
    while (ancestor !== null && ancestor !== root) {
      if (ancestor instanceof HTMLDetailsElement && !ancestor.open) {
        const summary = [...ancestor.children].find((child) => child.tagName === 'SUMMARY');
        if (summary === undefined || !summary.contains(node)) return false;
      }
      ancestor = ancestor.parentElement;
    }
    return true;
  });
};

export const nextFocusIndex = (
  count: number,
  current: number,
  backwards: boolean
): number => {
  if (count === 0) {
    return -1;
  }
  if (current < 0) {
    return backwards ? count - 1 : 0;
  }
  return backwards ? (current - 1 + count) % count : (current + 1) % count;
};

export const useFocusTrap = (
  ref: RefObject<HTMLElement | null>,
  active: boolean,
  onEscape: () => void
): void => {
  useEffect(() => {
    const root = ref.current;
    if (!active || root === null) {
      return;
    }
    const previous = document.activeElement;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault();
        onEscape();
        return;
      }
      if (event.key !== 'Tab') {
        return;
      }
      const nodes = focusableWithin(root);
      if (nodes.length === 0) {
        event.preventDefault();
        return;
      }
      const current = nodes.indexOf(document.activeElement as HTMLElement);
      const index = nextFocusIndex(nodes.length, current, event.shiftKey);
      event.preventDefault();
      nodes[index]?.focus();
    };
    root.addEventListener('keydown', onKeyDown);
    return () => {
      root.removeEventListener('keydown', onKeyDown);
      if (previous instanceof HTMLElement && document.contains(previous)) {
        previous.focus();
      }
    };
  }, [ref, active, onEscape]);
};
