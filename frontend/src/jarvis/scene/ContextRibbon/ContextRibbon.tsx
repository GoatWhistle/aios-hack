import { useId, useRef, useState } from 'react';
import { useI18n } from '@/shared/i18n/I18nContext';
import { DASH, formatStepDate } from '@/shared/lib/format';
import { useJarvisSessionContext, useJarvisVoice } from '@/jarvis/provider/contexts';
import './ContextRibbon.css';

interface ContextRibbonProps {
  speaking: boolean;
  onStop: () => void;
  onReadAll: () => void;
  canRestorePrevious: boolean;
  onRestorePrevious: () => void;
}

export const ContextRibbon = ({
  speaking,
  onStop,
  onReadAll,
  canRestorePrevious,
  onRestorePrevious
}: ContextRibbonProps) => {
  const { lang, t, toggleLang } = useI18n();
  const { askContext, scenes } = useJarvisSessionContext();
  const { speakEnabled, toggleSpeak, confirmVoice, toggleConfirmVoice } = useJarvisVoice();
  const [settingsOpen, setSettingsOpen] = useState(false);
  const settingsButtonRef = useRef<HTMLButtonElement>(null);
  const settingsRef = useRef<HTMLDivElement>(null);
  const settingsId = useId();

  const toggleSettings = () => {
    const popover = settingsRef.current;
    const anchor = settingsButtonRef.current;
    if (popover === null || anchor === null) {
      return;
    }
    if (settingsOpen) {
      popover.hidePopover?.();
      return;
    }
    const box = anchor.getBoundingClientRect();
    popover.style.setProperty('--settings-right', `${Math.round(window.innerWidth - box.right)}px`);
    popover.style.setProperty('--settings-top', `${Math.round(box.bottom)}px`);
    popover.showPopover?.();
  };

  const answer = scenes.scenes[scenes.activeIndex]?.answer ?? null;
  const context = askContext;
  const answeredContext = scenes.scenes[scenes.activeIndex]?.context;
  const differentContext =
    answeredContext !== undefined &&
    (answeredContext.scenario !== context.scenario ||
      (answeredContext.run_id ?? '') !== (context.run_id ?? '') ||
      answeredContext.step !== context.step ||
      (answeredContext.selected_well ?? '') !== (context.selected_well ?? ''));
  const date = context.date.length === 0 ? DASH : formatStepDate(lang, context.date);
  const well = context.selected_well ?? t('jarvis-screen.contextNoWell');

  return (
    <header className="jarvis-ribbon" aria-label={t('jarvis-screen.contextLabel')}>
      <div className="jarvis-ribbon-line">
        <p className="jarvis-ribbon-context">
          <span className="jarvis-ribbon-scenario">{context.scenario}</span>
          {context.run_id ? <span className="jarvis-ribbon-part">{context.run_id}</span> : null}
          <span className="jarvis-ribbon-part">
            {t('jarvis-screen.contextStep')} {context.step} · {date}
          </span>
          <span className="jarvis-ribbon-part">
            {t('jarvis-screen.contextWell')} {well}
          </span>
        </p>
        <div className="jarvis-ribbon-controls">
          <button
            type="button"
            className="jarvis-ribbon-button"
            disabled={!canRestorePrevious}
            onClick={onRestorePrevious}
          >
            {t('jarvis-screen.returnPreviousFocus')}
          </button>
          {speaking ? (
            <button type="button" className="jarvis-ribbon-button" onClick={onStop}>
              {t('jarvis-voice.speakStop')}
            </button>
          ) : answer === null || answer.trim().length === 0 ? null : (
            <button type="button" className="jarvis-ribbon-button" onClick={onReadAll}>
              {t('jarvis-voice.speakAnswer')}
            </button>
          )}
          <div className="jarvis-ribbon-settings">
            <button
              type="button"
              ref={settingsButtonRef}
              className="jarvis-ribbon-button"
              aria-haspopup="menu"
              aria-expanded={settingsOpen}
              aria-controls={settingsId}
              onClick={toggleSettings}
            >
              {t('jarvis-screen.settingsLabel')}
            </button>
            <div
              ref={settingsRef}
              id={settingsId}
              className="jarvis-ribbon-settings-body"
              popover="auto"
              role="menu"
              aria-label={t('jarvis-screen.settingsLabel')}
              onToggle={(event) => {
                setSettingsOpen(event.newState === 'open');
                if (event.newState === 'closed') {
                  const active = document.activeElement;
                  const outside = active !== null
                    && active !== document.body
                    && !settingsRef.current?.contains(active);
                  if (!outside) {
                    settingsButtonRef.current?.focus();
                  }
                }
              }}
            >
              <button
                role="menuitem"
                type="button"
                className="jarvis-ribbon-button"
                aria-pressed={confirmVoice}
                title={t('jarvis-voice.voiceModeHint')}
                onClick={toggleConfirmVoice}
              >
                {confirmVoice ? t('jarvis-voice.voiceConfirm') : t('jarvis-voice.voiceInstant')}
              </button>
              <button
                type="button"
                role="menuitem"
                className="jarvis-ribbon-button"
                aria-pressed={speakEnabled}
                onClick={toggleSpeak}
              >
                {speakEnabled ? t('jarvis-voice.speakOn') : t('jarvis-voice.speakOff')}
              </button>
              <button
                type="button"
                role="menuitem"
                className="jarvis-ribbon-button"
                onClick={toggleLang}
              >
                {lang === 'ru' ? 'en' : 'ru'}
              </button>
            </div>
          </div>
        </div>
      </div>
      {differentContext && answeredContext !== undefined ? (
        <p className="jarvis-ribbon-answer-context">
          {t('jarvis-screen.contextAnswerLabel')} {answeredContext.scenario}
          {answeredContext.run_id ? ` · ${answeredContext.run_id}` : ''}
          {' · '}
          {t('jarvis-screen.contextWell')}{' '}
          {answeredContext.selected_well ?? t('jarvis-screen.contextNoWell')}
          {' · '}
          {t('jarvis-screen.contextStep')} {answeredContext.step}
        </p>
      ) : null}
    </header>
  );
};
