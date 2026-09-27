import { useCallback } from 'react';
import { useI18n } from '@/shared/i18n/I18nContext';
import { useTimeline } from '@/entities/timeline/model/TimelineContext';
import { useOptionalJarvisSession } from '@/jarvis/provider/contexts';

export interface ExplainTarget {
  well: string;
  step: number;
}

export const useExplainAction = (): ((target: ExplainTarget) => void) | null => {
  const jarvis = useOptionalJarvisSession();
  const { t } = useI18n();
  const { timeline } = useTimeline();

  const run = useCallback(
    (target: ExplainTarget) => {
      if (jarvis === null) {
        return;
      }
      const steps = timeline.status === 'ready' ? timeline.data.steps : [];
      const step = steps[target.step];
      const context = {
        ...jarvis.askContext,
        step: step?.control_step ?? target.step,
        date: step?.date ?? '',
        selected_well: target.well,
        context_version: JSON.stringify([
          jarvis.askContext.scenario,
          jarvis.askContext.run_id ?? null,
          step?.control_step ?? target.step,
          step?.date ?? '',
          target.well,
          jarvis.askContext.workspace,
          jarvis.askContext.view
        ])
      };
      jarvis.open();
      jarvis.askQuestion(t('jarvis-stage.explainQuestion', { well: target.well }), context);
    },
    [jarvis, timeline, t]
  );

  return jarvis === null ? null : run;
};
