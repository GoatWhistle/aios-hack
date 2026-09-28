import { CaretRightIcon } from '@phosphor-icons/react';
import { useEffect, useId, useRef, useState } from 'react';
import { useT } from '@/shared/i18n/I18nContext';
import { latinKeyOf } from '@/shared/lib/keyboard/layout';
import { Markdown } from '@/jarvis/markdown/Markdown/Markdown';
import type { Scene } from '@/jarvis/model/scenes';
import './AnswerPanel.css';

export const firstLineOf = (source: string): string => {
  for (const line of source.split('\n')) {
    const text = line.replace(/^[#>\s*_-]+/, '').trim();
    if (text.length > 0) {
      return text;
    }
  }
  return '';
};

export const AnswerPanel = ({ scene }: { scene: Scene | null }) => {
  const t = useT();
  const [expanded, setExpanded] = useState(true);
  const [mounted, setMounted] = useState(true);
  const bodyRef = useRef<HTMLDivElement>(null);
  const bodyId = useId();
  const source = scene?.answer ?? scene?.answerDraft ?? '';
  const sceneId = scene?.id ?? null;

  useEffect(() => {
    setExpanded(true);
    setMounted(true);
  }, [sceneId]);

  useEffect(() => {
    if (expanded) {
      setMounted(true);
      return;
    }
    const node = bodyRef.current;
    const fading =
      node !== null &&
      typeof node.getAnimations === 'function' &&
      node.getAnimations().some(
        (running) => running instanceof CSSTransition && running.transitionProperty === 'opacity'
      );
    if (node === null || !fading) {
      setMounted(false);
      return;
    }
    const settle = (event: TransitionEvent) => {
      if (event.target === node && event.propertyName === 'opacity') {
        setMounted(false);
      }
    };
    node.addEventListener('transitionend', settle);
    return () => node.removeEventListener('transitionend', settle);
  }, [expanded]);

  useEffect(() => {
    if (source.length === 0) {
      return;
    }
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.target instanceof HTMLTextAreaElement || event.target instanceof HTMLInputElement) {
        return;
      }
      if (event.target instanceof HTMLElement && event.target.isContentEditable) {
        return;
      }
      if (event.ctrlKey || event.metaKey || event.altKey) {
        return;
      }
      if (latinKeyOf(event.key) === 'a') {
        event.preventDefault();
        setExpanded((value) => !value);
      }
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [source.length]);

  if (source.trim().length === 0) {
    return null;
  }

  return (
    <section className="jarvis-answer" data-expanded={expanded ? 'true' : undefined}>
      <button
        type="button"
        className="jarvis-answer-toggle"
        aria-expanded={expanded}
        aria-controls={bodyId}
        onClick={() => setExpanded((value) => !value)}
      >
        <CaretRightIcon size={14} weight="bold" aria-hidden="true" />
        <span className="jarvis-answer-lead">
          {mounted ? t('jarvis-screen.answerLabel') : firstLineOf(source)}
        </span>
        <kbd className="jarvis-answer-key">A</kbd>
      </button>
      <div
        className="jarvis-answer-body"
        id={bodyId}
        ref={bodyRef}
        data-open={expanded ? 'true' : 'false'}
        inert={!expanded}
        hidden={!mounted}
      >
        <Markdown source={source} />
      </div>
    </section>
  );
};
