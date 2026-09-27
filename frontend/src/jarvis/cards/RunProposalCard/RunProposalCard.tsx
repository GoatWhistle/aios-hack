import { useEffect, useState } from 'react';
import type { ConsoleAction } from '@/jarvis/actions/lib/consoleAction';
import { EmptyPayload } from '@/jarvis/cards/EmptyPayload/EmptyPayload';
import { isNum, isRecord, isStr } from '@/jarvis/cards/payloads/payloadPrimitives';
import type { CardType } from '@/jarvis/transport/events';
import type { LiveRun } from '@/pages/money-constraints/model/runTypes';
import { formatNumber, formatQuantity } from '@/shared/lib/format';
import { useI18n } from '@/shared/i18n/I18nContext';
import './RunProposalCard.css';

const POLL_MS = 3000;
const BUDGETS = [10, 30, 120] as const;

interface CaseProposal {
  request_id: string;
  request: string;
  scenario: string;
  operation: string;
  constraints: Record<string, unknown>;
  base_constraints: Record<string, unknown>;
  well?: string;
  date_from?: string;
  date_to?: string;
  section?: string;
  year?: number;
  before?: number;
  after?: number;
  unit?: string;
}

interface AlternativeProposal {
  request_id: string;
  source_run_id: string;
  source_manifest_hash: string;
  source_economics_hash: string;
  source_schedule_hash: string;
  alternative_schedule_hash: string;
  constraints_hash: string;
  source_npv_rub: number;
  additional_opm_evaluations: number;
  action: {
    well: string;
    from_step: number;
    through_step: number;
    original_target_m3_per_day: number;
    alternative_target_m3_per_day: number;
  };
}

interface RecordedComparison {
  status: string;
  npv_delta_rub: number | null;
  reason: string | null;
}

const readCase = (value: unknown): CaseProposal | null => {
  if (!isRecord(value) || !isStr(value.request_id) || !isStr(value.request)
    || !isStr(value.scenario) || !isStr(value.operation)
    || !isRecord(value.constraints) || !isRecord(value.base_constraints)
    || value.requires_confirmation !== true) return null;
  return value as unknown as CaseProposal;
};

const readAlternative = (value: unknown): AlternativeProposal | null => {
  if (!isRecord(value) || !isStr(value.request_id) || !isStr(value.source_run_id)
    || !isStr(value.source_manifest_hash) || !isStr(value.source_economics_hash)
    || !isStr(value.source_schedule_hash) || !isStr(value.alternative_schedule_hash)
    || !isStr(value.constraints_hash) || !isNum(value.source_npv_rub)
    || !isNum(value.additional_opm_evaluations) || !isRecord(value.action)
    || !isStr(value.action.well) || !isNum(value.action.from_step)
    || !isNum(value.action.through_step)
    || !isNum(value.action.original_target_m3_per_day)
    || !isNum(value.action.alternative_target_m3_per_day)
    || value.requires_confirmation !== true) return null;
  return value as unknown as AlternativeProposal;
};

interface Props {
  type: Extract<CardType, 'case-proposal' | 'alternative-proposal'>;
  payload: unknown;
  onOpen: (action: ConsoleAction) => void;
}

const RunProposal = ({ type, payload, onOpen }: Props) => {
  const { lang, t } = useI18n();
  const proposal = type === 'case-proposal' ? readCase(payload) : readAlternative(payload);
  const [run, setRun] = useState<LiveRun | null>(null);
  const [budget, setBudget] = useState<number>(30);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState('');
  const [pollError, setPollError] = useState('');
  const [comparison, setComparison] = useState<RecordedComparison | null>(null);
  const requestId = proposal?.request_id;

  useEffect(() => {
    if (requestId === undefined || (run !== null && run.status !== 'running')) return;
    let active = true;
    const load = async () => {
      try {
        const response = await fetch(`/api/runs/by-request/${encodeURIComponent(requestId)}`);
        if (response.status === 404) {
          if (active) setPollError('');
          return;
        }
        if (!response.ok) throw new Error(t('jarvis-cards.proposalUnavailable'));
        const value = await response.json() as LiveRun;
        if (!isStr(value.run_id)) throw new Error(t('jarvis-cards.proposalUnavailable'));
        if (active) {
          setRun(value);
          setPollError('');
        }
      } catch {
        if (active) setPollError(t('jarvis-cards.proposalUnavailable'));
      }
    };
    void load();
    const interval = window.setInterval(() => void load(), POLL_MS);
    return () => { active = false; window.clearInterval(interval); };
  }, [requestId, run?.status, t]);

  useEffect(() => {
    if (!run?.comparison_available || type !== 'alternative-proposal') return;
    let active = true;
    const load = async () => {
      try {
        const response = await fetch(`/api/runs/${encodeURIComponent(run.run_id)}/comparison`);
        if (!response.ok) return;
        const value = await response.json() as { comparison?: unknown };
        if (active && isRecord(value.comparison) && isStr(value.comparison.status)) {
          setComparison({
            status: value.comparison.status,
            npv_delta_rub: isNum(value.comparison.npv_delta_rub) ? value.comparison.npv_delta_rub : null,
            reason: isStr(value.comparison.reason) ? value.comparison.reason : null
          });
        }
      } catch {
        // The saved comparison link remains available for a later retry.
      }
    };
    void load();
    return () => { active = false; };
  }, [run?.comparison_available, run?.run_id, type]);

  if (proposal === null) return <EmptyPayload />;

  const confirm = async () => {
    if (run !== null || sending) return;
    setSending(true);
    setError('');
    const body = type === 'case-proposal'
      ? {
          mode: 'search', budget,
          constraints: (proposal as CaseProposal).constraints,
          case_request: {
            request_id: proposal.request_id,
            request: (proposal as CaseProposal).request,
            scenario: (proposal as CaseProposal).scenario,
            base_constraints: (proposal as CaseProposal).base_constraints
          }
        }
      : {
          mode: 'alternative',
          alternative_request: {
            request_id: proposal.request_id,
            source_run_id: (proposal as AlternativeProposal).source_run_id,
            well: (proposal as AlternativeProposal).action.well,
            control_step: (proposal as AlternativeProposal).action.from_step,
            target_m3_per_day: (proposal as AlternativeProposal).action.alternative_target_m3_per_day,
            source_manifest_hash: (proposal as AlternativeProposal).source_manifest_hash,
            source_economics_hash: (proposal as AlternativeProposal).source_economics_hash,
            source_schedule_hash: (proposal as AlternativeProposal).source_schedule_hash,
            alternative_schedule_hash: (proposal as AlternativeProposal).alternative_schedule_hash,
            constraints_hash: (proposal as AlternativeProposal).constraints_hash
          }
        };
    try {
      const response = await fetch('/api/runs', {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body)
      });
      const value = await response.json() as LiveRun & { error?: string; message?: string };
      if (!response.ok || !isStr(value.run_id)) throw new Error(value.message ?? value.error ?? t('jarvis-cards.proposalStartFailed'));
      setRun(value);
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : t('jarvis-cards.proposalStartFailed'));
    } finally {
      setSending(false);
    }
  };

  const cancel = async () => {
    if (run === null || run.status !== 'running') return;
    setSending(true);
    setError('');
    try {
      const response = await fetch(`/api/runs/${encodeURIComponent(run.run_id)}`, { method: 'DELETE' });
      const value = await response.json() as LiveRun & { error?: string; message?: string };
      if (!response.ok) throw new Error(value.message ?? value.error ?? t('jarvis-cards.proposalCancelFailed'));
      setRun(value);
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : t('jarvis-cards.proposalCancelFailed'));
    } finally {
      setSending(false);
    }
  };

  return (
    <div className="jarvis-run-proposal">
      {type === 'case-proposal' ? (
        <>
          <p>{t('jarvis-cards.proposalCaseSource', { scenario: (proposal as CaseProposal).scenario })}</p>
          <p>{(proposal as CaseProposal).request}</p>
          <p>{(proposal as CaseProposal).operation === 'add_well_outage'
            ? t('jarvis-cards.proposalOutage', {
                well: (proposal as CaseProposal).well ?? '',
                from: (proposal as CaseProposal).date_from ?? '',
                to: (proposal as CaseProposal).date_to ?? ''
              })
            : t('jarvis-cards.proposalLimit', {
                section: (proposal as CaseProposal).section === 'injection_limits'
                  ? t('jarvis-cards.proposalInjection')
                  : (proposal as CaseProposal).section === 'liquid_limits'
                    ? t('jarvis-cards.proposalLiquid')
                    : (proposal as CaseProposal).section ?? '',
                year: (proposal as CaseProposal).year ?? '',
                before: (proposal as CaseProposal).before ?? t('jarvis-cards.proposalUnset'),
                after: (proposal as CaseProposal).after ?? '',
                unit: (proposal as CaseProposal).unit === 'm3/day'
                  ? t('jarvis-cards.proposalRateUnit')
                  : (proposal as CaseProposal).unit ?? ''
              })}</p>
          {run === null && <label>{t('jarvis-cards.proposalBudget')}{' '}
            <select value={budget} onChange={(event) => setBudget(Number(event.target.value))} disabled={sending}>
              {BUDGETS.map((value) => <option key={value} value={value}>{value}</option>)}
            </select>
          </label>}
        </>
      ) : (
        <>
          <p>{t('jarvis-cards.proposalAlternativeSource', { run: (proposal as AlternativeProposal).source_run_id })}</p>
          <p>{t('jarvis-cards.proposalAlternativeAction', {
            well: (proposal as AlternativeProposal).action.well,
            from: (proposal as AlternativeProposal).action.from_step,
            through: (proposal as AlternativeProposal).action.through_step,
            before: formatNumber(lang, (proposal as AlternativeProposal).action.original_target_m3_per_day, 2),
            after: formatNumber(lang, (proposal as AlternativeProposal).action.alternative_target_m3_per_day, 2)
          })}</p>
          <p>{t('jarvis-cards.proposalAlternativeCost', {
            count: (proposal as AlternativeProposal).additional_opm_evaluations,
            npv: formatQuantity(lang, (proposal as AlternativeProposal).source_npv_rub, 'RUB')
          })}</p>
        </>
      )}
      {run === null && <p>{t('jarvis-cards.proposalConfirmHint')}</p>}
      {run === null ? (
        <button type="button" disabled={sending} onClick={() => void confirm()}>
          {sending ? t('jarvis-cards.proposalStarting') : t('jarvis-cards.proposalConfirm')}
        </button>
      ) : (
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
          {run.status === 'running' && !run.cancel_requested && <button type="button" disabled={sending} onClick={() => void cancel()}>{t('jarvis-cards.proposalCancel')}</button>}
          {run.manifest && <p>{t('jarvis-cards.proposalSound')}: {run.manifest.sound === true ? t('jarvis-cards.yes') : run.manifest.sound === false ? t('jarvis-cards.no') : t('jarvis-cards.proposalUnknown')}</p>}
          {run.manifest?.predicted_npv != null && <p>{t('jarvis-cards.runPredicted')}: {formatQuantity(lang, run.manifest.predicted_npv, 'RUB')}</p>}
          {run.manifest?.verified_npv != null && <p>{t('jarvis-cards.runVerified')}: {formatQuantity(lang, run.manifest.verified_npv, 'RUB')}</p>}
          {comparison && <p title={comparison.reason ?? undefined}>{comparison.status === 'comparable' && comparison.npv_delta_rub !== null
            ? t('jarvis-cards.proposalComparable', { delta: formatQuantity(lang, comparison.npv_delta_rub, 'RUB') })
            : t('jarvis-cards.proposalNotComparable')}</p>}
          {run.comparison_available === true && <a href={`/api/runs/${encodeURIComponent(run.run_id)}/comparison`}>{t('jarvis-cards.proposalComparison')}</a>}
          <button type="button" onClick={() => onOpen({ workspace: 'money', view: 'constraints' })}>{t('jarvis-cards.proposalOpenRuns')}</button>
        </div>
      )}
      {error && <p role="alert">{error}</p>}
      {pollError && <p role="alert">{pollError}</p>}
    </div>
  );
};

export const RunProposalCard = (props: Props) => (
  <RunProposal
    key={isRecord(props.payload) && isStr(props.payload.request_id) ? props.payload.request_id : 'invalid'}
    {...props}
  />
);
