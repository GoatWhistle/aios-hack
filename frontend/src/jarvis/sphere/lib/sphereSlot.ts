export interface SlotRect {
  left: number;
  top: number;
  width: number;
  height: number;
}

export const centerOf = (rect: SlotRect): { x: number; y: number } => ({
  x: rect.left + rect.width / 2,
  y: rect.top + rect.height / 2
});

const LAYOUT_PROPERTY = /^(width|height|min-|max-|top|left|right|bottom|inset|margin|padding|grid|flex|gap|place)/;

const settleLayoutTransitions = (element: Element): void => {
  if (typeof CSSTransition === 'undefined') {
    return;
  }
  for (let node: Element | null = element; node !== null; node = node.parentElement) {
    if (typeof node.getAnimations !== 'function') {
      return;
    }
    for (const running of node.getAnimations()) {
      if (running instanceof CSSTransition && LAYOUT_PROPERTY.test(running.transitionProperty)) {
        running.finish();
      }
    }
  }
};

export const readSlot = (element: Element | null): SlotRect | null => {
  if (element === null || typeof element.getBoundingClientRect !== 'function') {
    return null;
  }
  settleLayoutTransitions(element);
  const rect = element.getBoundingClientRect();
  if (rect.width <= 0 || rect.height <= 0) {
    return null;
  }
  return { left: rect.left, top: rect.top, width: rect.width, height: rect.height };
};
