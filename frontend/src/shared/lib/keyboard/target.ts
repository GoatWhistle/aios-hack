const EDITABLE = new Set(['INPUT', 'TEXTAREA', 'SELECT']);

export const isEditableTarget = (target: EventTarget | null): boolean => {
  if (target === null || !(target instanceof HTMLElement)) {
    return false;
  }
  return EDITABLE.has(target.tagName) || target.isContentEditable === true;
};

export const isInteractiveTarget = (target: EventTarget | null): boolean =>
  isEditableTarget(target) || (target instanceof Element &&
    target.closest('button, a[href], summary, [role="button"], [role="listbox"], [role="combobox"], [role="slider"], [role="menuitem"]') !== null);

/** Console shortcuts yield to a mounted modal, regardless of event origin. */
export const hasOpenModalDialog = (): boolean =>
  [...document.querySelectorAll('[role="dialog"][aria-modal="true"]')]
    .some((dialog) => dialog.closest('[hidden], [inert], [aria-hidden="true"]') === null);

export const isInsideScroller = (target: EventTarget | null): boolean => {
  let node = target instanceof HTMLElement ? target : null;
  while (node !== null) {
    if (node.scrollHeight > node.clientHeight + 1) {
      const overflow = getComputedStyle(node).overflowY;
      if (overflow === 'auto' || overflow === 'scroll') {
        return true;
      }
    }
    node = node.parentElement;
  }
  return false;
};
