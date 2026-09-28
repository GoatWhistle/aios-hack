import { useEffect, useId, useMemo, useRef, useState, type KeyboardEvent } from 'react';
import { useI18n } from '@/shared/i18n/I18nContext';
import { useJarvisSessionContext } from '@/jarvis/provider/contexts';
import { fetchSessionRows, type SessionRow } from '@/jarvis/model/sessions';
import {
  buildChoices,
  groupChoices,
  labelOf,
  NEW_SESSION,
  type SessionChoice
} from '@/jarvis/scene/HistorySessions/sessionChoices';
import './HistorySessions.css';

export const HistorySessions = () => {
  const { lang, t } = useI18n();
  const { sessionId, loadSession, startSession, visible, scenes } = useJarvisSessionContext();
  const [rows, setRows] = useState<SessionRow[]>([]);
  const [open, setOpen] = useState(false);
  const [cursor, setCursor] = useState(0);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const popoverRef = useRef<HTMLDivElement>(null);
  const listId = useId();

  useEffect(() => {
    if (!visible) {
      return;
    }
    let alive = true;
    void fetchSessionRows().then((next) => {
      if (alive) {
        setRows(next);
      }
    });
    return () => {
      alive = false;
    };
  }, [visible, scenes.scenes.length]);

  const choices = useMemo<SessionChoice[]>(
    () =>
      buildChoices(rows, lang, {
        today: t('jarvis-rail.sessionToday'),
        yesterday: t('jarvis-rail.sessionYesterday'),
        noQuestion: t('jarvis-rail.sessionNoQuestion'),
        newSession: t('jarvis-rail.sessionNew')
      }, new Date()),
    [rows, lang, t]
  );
  const groups = useMemo(() => groupChoices(choices), [choices]);
  const currentIndex = Math.max(0, choices.findIndex((choice) => choice.id === sessionId));
  const current = choices[currentIndex] ?? choices[0];

  const close = (refocus: boolean) => {
    setOpen(false);
    popoverRef.current?.hidePopover?.();
    if (refocus) {
      buttonRef.current?.focus();
    }
  };

  const pick = (index: number) => {
    const choice = choices[index];
    if (choice === undefined) {
      return;
    }
    close(true);
    if (choice.id === NEW_SESSION) {
      startSession();
      return;
    }
    loadSession(choice.id);
  };

  const place = () => {
    const anchor = buttonRef.current?.getBoundingClientRect();
    const popover = popoverRef.current;
    if (anchor === undefined || popover === null) {
      return;
    }
    popover.style.setProperty('--sessions-right', `${Math.round(window.innerWidth - anchor.right)}px`);
    popover.style.setProperty('--sessions-bottom', `${Math.round(window.innerHeight - anchor.top)}px`);
    popover.style.setProperty('--sessions-width', `${Math.round(anchor.width)}px`);
  };

  const toggle = () => {
    if (open) {
      close(false);
      return;
    }
    setCursor(currentIndex);
    place();
    setOpen(true);
    popoverRef.current?.showPopover?.();
  };

  useEffect(() => {
    if (!open) {
      return;
    }
    const node = popoverRef.current?.querySelector<HTMLElement>('[data-cursor="true"]');
    node?.scrollIntoView({ block: 'nearest' });
    popoverRef.current?.focus();
  }, [open, cursor]);

  useEffect(() => {
    popoverRef.current?.hidePopover?.();
    setOpen(false);
  }, [scenes.scenes.length]);

  useEffect(() => {
    const anchor = buttonRef.current;
    if (!open || anchor === null) {
      return;
    }
    let frame = 0;
    let last = '';
    const watch = () => {
      const box = anchor.getBoundingClientRect();
      const key = `${Math.round(box.right)}:${Math.round(box.top)}:${Math.round(box.width)}`;
      if (key !== last) {
        last = key;
        place();
      }
      frame = requestAnimationFrame(watch);
    };
    frame = requestAnimationFrame(watch);
    return () => cancelAnimationFrame(frame);
  }, [open]);

  useEffect(() => {
    if (!open) {
      return;
    }
    const guard = (event: globalThis.KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault();
        event.stopPropagation();
        close(true);
      }
    };
    window.addEventListener('keydown', guard, true);
    return () => window.removeEventListener('keydown', guard, true);
  }, [open]);

  const onKeyDown = (event: KeyboardEvent<HTMLElement>) => {
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault();
      if (!open) {
        toggle();
        return;
      }
      const delta = event.key === 'ArrowDown' ? 1 : -1;
      setCursor((value) => Math.min(choices.length - 1, Math.max(0, value + delta)));
      return;
    }
    if (open && event.key === 'Home') {
      event.preventDefault();
      setCursor(0);
      return;
    }
    if (open && event.key === 'End') {
      event.preventDefault();
      setCursor(choices.length - 1);
      return;
    }
    if (open && (event.key === 'Enter' || event.key === ' ')) {
      event.preventDefault();
      pick(cursor);
    }
  };

  const option = (choice: SessionChoice, index: number) => (
    <button
      type="button"
      key={choice.id === NEW_SESSION ? 'new' : choice.id}
      id={`${listId}-${index}`}
      className="jarvis-sessions-option"
      role="option"
      aria-selected={index === currentIndex}
      data-cursor={index === cursor ? 'true' : undefined}
      data-new={choice.id === NEW_SESSION ? 'true' : undefined}
      title={labelOf(choice)}
      onMouseEnter={() => setCursor(index)}
      onClick={() => pick(index)}
    >
      <span className="jarvis-sessions-option-question">{choice.question}</span>
      {choice.time.length === 0 ? null : (
        <span className="jarvis-sessions-option-meta">
          <span className="jarvis-sessions-option-time">{choice.time}</span>
          <span className="jarvis-sessions-option-scenes">
            {t('jarvis-rail.sessionScenes', { count: choice.scenes })}
          </span>
        </span>
      )}
    </button>
  );

  return (
    <div className="jarvis-sessions">
      <button
        type="button"
        ref={buttonRef}
        className="jarvis-sessions-button"
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-label={t('jarvis-rail.sessionsPick', { session: labelOf(current) })}
        aria-controls={listId}
        title={labelOf(current)}
        onClick={toggle}
        onKeyDown={onKeyDown}
      >
        <span className="jarvis-sessions-name">{t('jarvis-rail.sessionsLabel')}</span>
        <span className="jarvis-sessions-value">{current?.question}</span>
        <span className="jarvis-sessions-caret" aria-hidden="true" />
      </button>
      <div
        ref={popoverRef}
        id={listId}
        className="jarvis-sessions-popover"
        popover="auto"
        role="listbox"
        tabIndex={-1}
        aria-label={t('jarvis-rail.sessionsLabel')}
        aria-activedescendant={open ? `${listId}-${cursor}` : undefined}
        onToggle={(event) => {
          setOpen(event.newState === 'open');
        }}
        onKeyDown={onKeyDown}
      >
        {choices[0] === undefined ? null : option(choices[0], 0)}
        {groups.map((group) => (
          <div className="jarvis-sessions-group" key={group.day} role="presentation">
            <span className="jarvis-sessions-day">{group.day}</span>
            {group.items.map((choice) =>
              option(choice, choices.findIndex((entry) => entry.id === choice.id))
            )}
          </div>
        ))}
      </div>
    </div>
  );
};
