import { useEffect, useLayoutEffect, useRef, useState, type KeyboardEvent, type ReactNode } from 'react';
import { useT } from '@/shared/i18n/I18nContext';
import { QUESTION_LIMIT } from '@/jarvis/transport/JarvisTransport';
import { MicButton } from '@/jarvis/voice/MicButton/MicButton';
import './InputDock.css';

interface InputDockProps {
  onAsk: (question: string) => void;
  focusSignal: number;
  history: readonly string[];
  sessionId?: string;
  busy?: boolean;
  onCancel?: () => void;
  draft?: string;
  onDraftChange?: (text: string) => void;
  lead?: ReactNode;
  trail?: ReactNode;
}

const COUNTER_FROM = Math.round(QUESTION_LIMIT * 0.8);
const GROW_LINES = 5;

export const recallAt = (
  history: readonly string[],
  cursor: number
): { text: string; cursor: number } => {
  if (history.length === 0) {
    return { text: '', cursor: -1 };
  }
  const next = Math.min(cursor + 1, history.length - 1);
  return { text: history[history.length - 1 - next], cursor: next };
};

export const InputDock = ({ onAsk, focusSignal, history, sessionId, busy = false, onCancel, draft, onDraftChange, lead, trail }: InputDockProps) => {
  const t = useT();
  const [localText, setLocalText] = useState('');
  const text = draft ?? localText;
  const setText = (value: string) => {
    const bounded = value.slice(0, QUESTION_LIMIT);
    if (onDraftChange) onDraftChange(bounded);
    else setLocalText(bounded);
  };
  const [cursor, setCursor] = useState(-1);
  const ref = useRef<HTMLTextAreaElement>(null);

  const historyContent = JSON.stringify(history);
  useEffect(() => { setCursor(-1); }, [historyContent, sessionId]);

  useEffect(() => {
    if (focusSignal > 0) {
      ref.current?.focus();
    }
  }, [focusSignal]);

  useLayoutEffect(() => {
    const node = ref.current;
    if (node === null) {
      return;
    }
    node.style.height = 'auto';
    const line = Number.parseFloat(getComputedStyle(node).lineHeight) || 20;
    const cap = line * GROW_LINES;
    node.style.height = `${Math.min(node.scrollHeight, cap)}px`;
  }, [text]);

  const submit = () => {
    const trimmed = text.trim();
    if (trimmed.length === 0 || busy) {
      return;
    }
    onAsk(trimmed);
    setText('');
    setCursor(-1);
  };

  const onKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.nativeEvent.isComposing || event.keyCode === 229) return;
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      submit();
      return;
    }
    if (event.key === 'ArrowUp' && (text.length === 0 || cursor >= 0)) {
      const recalled = recallAt(history, cursor);
      if (recalled.cursor < 0) {
        return;
      }
      event.preventDefault();
      setText(recalled.text);
      setCursor(recalled.cursor);
      return;
    }
    if (event.key === 'ArrowDown' && cursor >= 0) {
      event.preventDefault();
      const next = cursor - 1;
      setCursor(next);
      setText(next < 0 ? '' : history[history.length - 1 - next] ?? '');
    }
  };

  const empty = text.trim().length === 0;

  return (
    <div className="jarvis-dock-row">
      <form
        className="jarvis-dock"
        data-busy={busy ? 'true' : undefined}
        onSubmit={(event) => {
          event.preventDefault();
          submit();
        }}
      >
        {lead}
        <textarea
          ref={ref}
          className="jarvis-dock-input"
          rows={1}
          aria-label={t('jarvis-screen.inputLabel')}
          placeholder={t('jarvis-screen.inputPlaceholder')}
          maxLength={QUESTION_LIMIT}
          value={text}
          onChange={(event) => {
            setText(event.target.value.slice(0, QUESTION_LIMIT));
            setCursor(-1);
          }}
          onKeyDown={onKeyDown}
        />
        {text.length >= COUNTER_FROM ? (
          <span className="jarvis-dock-count" role="status" aria-live="polite">
            {t('jarvis-screen.limit', { count: text.length })}
          </span>
        ) : null}
        <MicButton
          onTranscript={(value) => {
            setText(value);
            setCursor(-1);
          }}
          onCommit={(value) => {
            const question = value.trim().slice(0, QUESTION_LIMIT);
            setCursor(-1);
            if (busy) setText(question);
            else if (question.length > 0) {
              onAsk(question);
              setText('');
            }
          }}
        />
        {busy && onCancel ? (
          <button type="button" className="jarvis-dock-cancel" onClick={onCancel}>
            {t('jarvis-screen.walk.stop')}
          </button>
        ) : null}
        <button
          type="submit"
          className="jarvis-dock-send"
          disabled={busy || empty}
          title={empty ? t('jarvis-screen.sendHint') : undefined}
        >
          {t('jarvis-screen.send')}
        </button>
      </form>
      {trail}
    </div>
  );
};
