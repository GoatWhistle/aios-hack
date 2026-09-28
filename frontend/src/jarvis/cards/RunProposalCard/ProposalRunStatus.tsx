import { formatQuantity } from '@/shared/lib/format';
import { useI18n } from '@/shared/i18n/I18nContext';
import type { ConsoleAction } from '@/jarvis/actions/lib/consoleAction';
import type { LiveRun } from '@/pages/money-constraints/model/runTypes';
import type { RecordedComparison } from '@/jarvis/cards/RunProposalCard/proposalPayload';

interface ProposalRunStatusProps {
  run: LiveRun;
  comparison: RecordedComparison | null;
  sending: boolean;
  onCancel: () => void;
  onOpen: (action: ConsoleAction) => void;
}

export const ProposalRunStatus = ({ run, comparison, sending, onCancel, onOpen }: ProposalRunStatusProps) => {
  const { lang, t } = useI18n();
  const soundLabel = run.manifest?.sound === true
    ? t('jarvis-cards.yes')
    : run.manifest?.sound === false
      ? t('jarvis-cards.no')
      : t('jarvis-cards.proposalUnknown');

  return (
    <div role="status">
      <p>{t('jarvis-cards.proposalRunId', { id: run.run_id })}</p>
      <p>{run.message_key && t(run.message_key) !== run.message_key ? t(run.message_key) : run.message || run.status}</p>
      {run.progress && <progress value={run.progress.step} max={run.progress.total} aria-label={t('jarvis-cards.proposalProgress')} />}
      {run.progress && <p>{t('jarvis-cards.proposalProgressSteps', { step: run.progress.step, total: run.progress.total })}</p>}
      {run.evaluations != null && <p>{t('runs.evaluations', { count: run.evaluations, feasible: run.feasible_evaluations ?? 0 })}</p>}
      {run.rejection_reasons && run.rejection_reasons.length > 0 && (
        <details open={run.status === 'failed'}>
          <summary>{t('jarvis-cards.proposalRejections')}</summary>
          <ul>{run.rejection_reasons.slice(0, 5).map((reason, index) => <li key={index}>{reason}</li>)}</ul>
          <p>{t('jarvis-cards.proposalRejectionBoundary')}</p>
        </details>
      )}
      {run.status === 'running' && !run.cancel_requested && (
        <button type="button" disabled={sending} onClick={onCancel}>{t('jarvis-cards.proposalCancel')}</button>
      )}
      {run.manifest && <p>{t('jarvis-cards.proposalSound')}: {soundLabel}</p>}
      {run.manifest?.predicted_npv != null && <p>{t('jarvis-cards.runPredicted')}: {formatQuantity(lang, run.manifest.predicted_npv, 'RUB')}</p>}
      {run.manifest?.verified_npv != null && <p>{t('jarvis-cards.runVerified')}: {formatQuantity(lang, run.manifest.verified_npv, 'RUB')}</p>}
      {comparison && <p title={comparison.reason ?? undefined}>{comparison.status === 'comparable' && comparison.npv_delta_rub !== null
        ? t('jarvis-cards.proposalComparable', { delta: formatQuantity(lang, comparison.npv_delta_rub, 'RUB') })
        : t('jarvis-cards.proposalNotComparable')}</p>}
      {run.comparison_available === true && <a href={`/api/runs/${encodeURIComponent(run.run_id)}/comparison`}>{t('jarvis-cards.proposalComparison')}</a>}
      <button type="button" onClick={() => onOpen({ workspace: 'money', view: 'constraints' })}>{t('jarvis-cards.proposalOpenRuns')}</button>
    </div>
  );
};
