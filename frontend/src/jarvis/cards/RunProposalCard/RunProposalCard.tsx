import { useEffect, useState } from 'react';
import type { ConsoleAction } from '@/jarvis/actions/lib/consoleAction';
import { EmptyPayload } from '@/jarvis/cards/EmptyPayload/EmptyPayload';
import { isNum, isRecord, isStr } from '@/jarvis/cards/payloads/payloadPrimitives';
import type { CardType } from '@/jarvis/transport/events';
import type { LiveRun } from '@/pages/money-constraints/model/runTypes';
import { useI18n } from '@/shared/i18n/I18nContext';
import {
  proposalRunBody,
  readAlternative,
  readCase,
  type AlternativeProposal,
  type CaseProposal,
  type RecordedComparison
} from '@/jarvis/cards/RunProposalCard/proposalPayload';
import { AlternativeSummary, CaseSummary } from '@/jarvis/cards/RunProposalCard/ProposalSummary';
import { ProposalRunStatus } from '@/jarvis/cards/RunProposalCard/ProposalRunStatus';
import './RunProposalCard.css';

const POLL_MS = 3000;
const BUDGETS = [10, 30, 120] as const;

interface Props {
  type: Extract<CardType, 'case-proposal' | 'alternative-proposal'>;
  payload: unknown;
  onOpen: (action: ConsoleAction) => void;
}

const RunProposal = ({ type, payload, onOpen }: Props) => {
  const t = useI18n().t;
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
        setComparison(null);
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
    try {
      const response = await fetch('/api/runs', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(proposalRunBody(type, proposal, budget))
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
      {type === 'case-proposal'
        ? <CaseSummary proposal={proposal as CaseProposal} />
        : <AlternativeSummary proposal={proposal as AlternativeProposal} />}
      {type === 'case-proposal' && run === null && (
        <label>{t('jarvis-cards.proposalBudget')}{' '}
          <select value={budget} onChange={(event) => setBudget(Number(event.target.value))} disabled={sending}>
            {BUDGETS.map((value) => <option key={value} value={value}>{value}</option>)}
          </select>
        </label>
      )}
      {run === null && <p>{t('jarvis-cards.proposalConfirmHint')}</p>}
      {run === null ? (
        <button type="button" disabled={sending} onClick={() => void confirm()}>
          {sending ? t('jarvis-cards.proposalStarting') : t('jarvis-cards.proposalConfirm')}
        </button>
      ) : (
        <ProposalRunStatus
          run={run}
          comparison={comparison}
          sending={sending}
          onCancel={() => void cancel()}
          onOpen={onOpen}
        />
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
