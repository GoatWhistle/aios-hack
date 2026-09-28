import { CaretLeftIcon, CaretRightIcon, CaretUpIcon } from '@phosphor-icons/react';
import { useCallback, useEffect, useRef, useState, type KeyboardEvent } from 'react';
import { useI18n } from '@/shared/i18n/I18nContext';
import type { Scene } from '@/jarvis/model/scenes';
import { beadTime, cropQuestion, glyphsOf } from '@/jarvis/scene/lib/cardGlyphs';
import { formatStepDate } from '@/shared/lib/format';
import { RailPreview, type RailPreviewData } from '@/jarvis/scene/HistoryRail/RailPreview';
import { useRailOverflow } from '@/jarvis/scene/HistoryRail/useRailOverflow';
import { Suggestions } from '@/jarvis/scene/Suggestions/Suggestions';
import './HistoryRail.css';
import './RailBead.css';

interface HistoryRailProps {
  scenes: readonly Scene[];
  activeIndex: number;
  onSelect: (index: number) => void;
  suggestions?: readonly string[];
  onPickSuggestion?: (text: string) => void;
}

export const HistoryRail = ({
  scenes,
  activeIndex,
  onSelect,
  suggestions = [],
  onPickSuggestion
}: HistoryRailProps) => {
  const { lang, t } = useI18n();
  const [preview, setPreview] = useState<RailPreviewData | null>(null);
  const [tipsOpen, setTipsOpen] = useState(true);
  const listRef = useRef<HTMLOListElement>(null);
  const beads = scenes
    .map((scene, index) => ({ scene, index }))
    .filter((entry) => entry.scene.question.trim().length > 0);
  const count = beads.length;
  const overflow = useRailOverflow(listRef, count);

  useEffect(() => {
    const list = listRef.current;
    const node = list?.querySelector<HTMLElement>('[data-active="true"]');
    if (list === null || list === undefined || node === null || node === undefined) {
      return;
    }
    const maximum = Math.max(0, list.scrollWidth - list.clientWidth);
    const centred = node.offsetLeft + node.offsetWidth / 2 - list.clientWidth / 2;
    list.scrollLeft = Math.max(0, Math.min(maximum, centred));
  }, [activeIndex, count]);

  const onWheel = useCallback((event: WheelEvent) => {
    const node = listRef.current;
    if (node === null) {
      return;
    }
    if (event.ctrlKey || event.metaKey || Math.abs(event.deltaX) > Math.abs(event.deltaY)) return;
    const maximum = Math.max(0, node.scrollWidth - node.clientWidth);
    const unit = event.deltaMode === 1 ? 32 : event.deltaMode === 2 ? node.clientWidth : 1;
    const next = Math.max(0, Math.min(maximum, node.scrollLeft + event.deltaY * unit));
    if (next !== node.scrollLeft) {
      event.preventDefault();
      node.scrollLeft = next;
    }
  }, []);

  useEffect(() => {
    const node = listRef.current;
    if (node === null) {
      return;
    }
    node.addEventListener('wheel', onWheel, { passive: false });
    return () => node.removeEventListener('wheel', onWheel);
  }, [onWheel]);

  const step = (delta: number) => {
    const at = beads.findIndex((entry) => entry.index === activeIndex);
    const next = beads[(at < 0 ? 0 : at) + delta];
    if (next !== undefined) {
      onSelect(next.index);
    }
  };

  const onKeyDown = (event: KeyboardEvent<HTMLOListElement>) => {
    if (event.key === 'ArrowRight') {
      event.preventDefault();
      step(1);
      return;
    }
    if (event.key === 'ArrowLeft') {
      event.preventDefault();
      step(-1);
      return;
    }
    if (event.key === 'Home') {
      event.preventDefault();
      if (beads[0] !== undefined) {
        onSelect(beads[0].index);
      }
      return;
    }
    if (event.key === 'End') {
      event.preventDefault();
      const last = beads[count - 1];
      if (last !== undefined) {
        onSelect(last.index);
      }
    }
  };

  const hasTips = suggestions.length > 0 && onPickSuggestion !== undefined;
  const show = (index: number, anchor: HTMLElement, scene: Scene, context: string) => {
    setPreview({
      index,
      anchor: anchor.getBoundingClientRect(),
      question: scene.question,
      glyphs: glyphsOf(scene.cards.map((entry) => entry.card.type)),
      caption: (scene.caption ?? scene.captionDraft).split('\n')[0] ?? '',
      context
    });
  };
  const hide = (index: number) => {
    setPreview((value) => (value === null || value.index === index ? null : value));
  };

  return (
    <div className="jarvis-rail" data-empty={count === 0 ? 'true' : undefined}>
      <div
        className="jarvis-rail-row"
        data-overflow-start={overflow.start ? 'true' : undefined}
        data-overflow-end={overflow.end ? 'true' : undefined}
      >
        {overflow.start ? (
          <button
            type="button"
            className="jarvis-rail-step"
            data-edge="start"
            aria-label={t('jarvis-rail.railOlder')}
            onClick={() => overflow.scrollBy(-1)}
          >
            <CaretLeftIcon size={14} weight="bold" aria-hidden="true" />
          </button>
        ) : null}
        <ol
          className="jarvis-rail-beads"
          ref={listRef}
          role="listbox"
          tabIndex={0}
          aria-label={t('jarvis-rail.railLabel')}
          aria-activedescendant={
            beads.some((entry) => entry.index === activeIndex)
              ? `jarvis-bead-${activeIndex}`
              : undefined
          }
          onKeyDown={onKeyDown}
          onScroll={() => setPreview(null)}
        >
          {beads.map(({ scene, index }) => {
            const active = index === activeIndex;
            const contextDetails = [
              scene.context.run_id ? `${t('jarvis-cards.runId')}: ${scene.context.run_id}` : null,
              `${t('jarvis-screen.contextWell')}: ${scene.context.selected_well ?? t('jarvis-screen.contextNoWell')}`,
              `${t('jarvis-screen.contextStep')} ${scene.context.step} · ${formatStepDate(lang, scene.context.date)}`,
              `${t('jarvis-screen.contextScenario')}: ${scene.context.scenario}`
            ]
              .filter((value): value is string => value !== null)
              .join(' · ');
            return (
              <li
                className="jarvis-rail-bead"
                key={scene.id}
                id={`jarvis-bead-${index}`}
                role="option"
                aria-selected={active}
                data-active={active ? 'true' : undefined}
              >
                <button
                  type="button"
                  className="jarvis-rail-button"
                  tabIndex={-1}
                  aria-label={t('jarvis-rail.railBead', {
                    question: scene.question,
                    context: contextDetails
                  })}
                  onClick={() => onSelect(index)}
                  onPointerEnter={(event) => show(index, event.currentTarget, scene, contextDetails)}
                  onPointerLeave={() => hide(index)}
                  onFocus={(event) => show(index, event.currentTarget, scene, contextDetails)}
                  onBlur={() => hide(index)}
                >
                  <span className="jarvis-rail-question">{cropQuestion(scene.question)}</span>
                  <span className="jarvis-rail-time">{beadTime(lang, scene.ts)}</span>
                </button>
              </li>
            );
          })}
        </ol>
        {overflow.end ? (
          <button
            type="button"
            className="jarvis-rail-step"
            data-edge="end"
            aria-label={t('jarvis-rail.railNewer')}
            onClick={() => overflow.scrollBy(1)}
          >
            <CaretRightIcon size={14} weight="bold" aria-hidden="true" />
          </button>
        ) : null}
        {hasTips ? (
          <button
            type="button"
            className="jarvis-rail-tips-toggle"
            aria-expanded={tipsOpen}
            aria-controls="jarvis-rail-tips-list"
            aria-label={t(
              tipsOpen ? 'jarvis-screen.suggestionsHide' : 'jarvis-screen.suggestionsShow'
            )}
            title={t(
              tipsOpen ? 'jarvis-screen.suggestionsHide' : 'jarvis-screen.suggestionsShow'
            )}
            onClick={() => setTipsOpen((value) => !value)}
          >
            <CaretUpIcon size={14} weight="bold" aria-hidden="true" />
          </button>
        ) : null}
      </div>
      {hasTips ? (
        <div
          className="jarvis-rail-tips-list"
          id="jarvis-rail-tips-list"
          data-open={tipsOpen ? 'true' : 'false'}
          inert={!tipsOpen}
        >
          <Suggestions items={suggestions} onPick={onPickSuggestion} />
        </div>
      ) : null}
      <RailPreview data={preview} />
    </div>
  );
};
