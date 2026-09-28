import { useMemo, useState } from 'react';
import { useI18n } from '@/shared/i18n/I18nContext';
import type { ConsoleAction } from '@/jarvis/actions/lib/consoleAction';
import type { JarvisAskContext } from '@/jarvis/transport/events';
import type { ScenesState } from '@/jarvis/model/scenes';
import './WalkthroughControls.css';

const STAGES = ['situation', 'constraint', 'decision', 'result', 'acceptance'] as const;
type Stage = (typeof STAGES)[number];
interface Walkthrough {
  well: string;
  context: JarvisAskContext;
  focus: ConsoleAction;
  indexes: number[];
  stage: number;
}

interface Props {
  scenes: ScenesState;
  context: JarvisAskContext;
  busy: boolean;
  askQuestion: (question: string, context?: JarvisAskContext) => void;
  selectScene: (index: number) => void;
  applyAction: (action: ConsoleAction) => void;
  cancel: () => void;
}

export const WalkthroughControls = ({ scenes, context, busy, askQuestion, selectScene, applyAction, cancel }: Props) => {
  const { t } = useI18n();
  const [walkthrough, setWalkthrough] = useState<Walkthrough | null>(null);
  const questions = useMemo<Record<Stage, (well: string, step: number, date: string) => string>>(() => ({
    situation: (well, step, date) => t('jarvis-screen.walk.situationQuestion', { well, step, date }),
    constraint: (well, step, date) => t('jarvis-screen.walk.constraintQuestion', { well, step, date }),
    decision: (well, step, date) => t('jarvis-screen.walk.decisionQuestion', { well, step, date }),
    result: (well, step, date) => t('jarvis-screen.walk.resultQuestion', { well, step, date }),
    acceptance: (well, step, date) => t('jarvis-screen.walk.acceptanceQuestion', { well, step, date })
  }), [t]);
  const currentIndex = walkthrough?.indexes[walkthrough.stage] ?? -1;
  const interrupted = walkthrough !== null && (
    (scenes.activeIndex >= 0 && scenes.activeIndex !== currentIndex) ||
    context.context_version !== walkthrough.context.context_version
  );
  const stage = walkthrough === null ? null : STAGES[walkthrough.stage];

  const askStage = (run: Walkthrough, index: number) => {
    const key = STAGES[index];
    if (key === undefined) return;
    applyAction(run.focus);
    askQuestion(questions[key](run.well, run.context.step, run.context.date), run.context);
  };

  const start = () => {
    if (context.selected_well === null) return;
    const focus: ConsoleAction = {
      scenario: context.scenario,
      run_id: context.run_id,
      workspace: context.workspace,
      view: context.view,
      step: context.step,
      well: context.selected_well
    };
    const run: Walkthrough = {
      well: context.selected_well,
      context: { ...context },
      focus,
      indexes: [scenes.scenes.length],
      stage: 0
    };
    setWalkthrough(run);
    askStage(run, 0);
  };

  const next = () => {
    if (walkthrough === null || busy || walkthrough.stage >= STAGES.length - 1) return;
    const index = walkthrough.stage + 1;
    const existing = walkthrough.indexes[index];
    if (existing !== undefined) {
      applyAction(walkthrough.focus);
      selectScene(existing);
      setWalkthrough({ ...walkthrough, stage: index });
      return;
    }
    askStage(walkthrough, index);
    setWalkthrough({ ...walkthrough, stage: index, indexes: [...walkthrough.indexes, scenes.scenes.length] });
  };

  const back = () => {
    if (walkthrough === null || busy || walkthrough.stage === 0) return;
    const index = walkthrough.stage - 1;
    applyAction(walkthrough.focus);
    selectScene(walkthrough.indexes[index] ?? 0);
    setWalkthrough({ ...walkthrough, stage: index });
  };

  const resume = () => {
    if (walkthrough === null) return;
    applyAction(walkthrough.focus);
    selectScene(currentIndex);
  };

  const stop = () => {
    cancel();
    if (walkthrough !== null) {
      applyAction(walkthrough.focus);
      selectScene(currentIndex);
    }
    setWalkthrough(null);
  };

  return (
    <div className="jarvis-walk" aria-label={t('jarvis-screen.walk.label')} role="group">
      {walkthrough === null ? (
        <button
          type="button"
          className="jarvis-walk-button"
          onClick={start}
          disabled={busy || context.selected_well === null}
          title={context.selected_well === null ? t('jarvis-screen.walk.selectWell') : undefined}
        >
          {t('jarvis-screen.walk.start')}
        </button>
      ) : (
        <>
          <span className="jarvis-walk-progress">
            {t('jarvis-screen.walk.progress', { current: walkthrough.stage + 1, total: STAGES.length, well: walkthrough.well })}
            {stage === null ? '' : ` · ${t(`jarvis-screen.walk.stage.${stage}`)}`}
          </span>
          {interrupted ? (
            <button type="button" className="jarvis-walk-button" onClick={resume} disabled={busy}>{t('jarvis-screen.walk.resume')}</button>
          ) : null}
          <button type="button" className="jarvis-walk-button" onClick={back} disabled={busy || interrupted || walkthrough.stage === 0}>{t('jarvis-screen.walk.back')}</button>
          <button type="button" className="jarvis-walk-button" onClick={next} disabled={busy || interrupted || walkthrough.stage >= STAGES.length - 1}>{t('jarvis-screen.walk.next')}</button>
          <button type="button" className="jarvis-walk-button" onClick={stop}>{t('jarvis-screen.walk.stop')}</button>
        </>
      )}
    </div>
  );
};
