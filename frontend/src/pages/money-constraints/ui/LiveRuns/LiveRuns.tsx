import { useEffect, useState } from 'react';
import { useFallbackI18n } from '@/shared/i18n/I18nContext';
import type { ConstraintsDoc } from '@/entities/scenarios/types';
import { useLiveRuns } from '@/pages/money-constraints/model/useLiveRuns';
import type { AlternativeRequest } from '@/pages/money-constraints/model/runTypes';
import { formatQuantity } from '@/shared/lib/format';
import { RunCard } from '@/pages/money-constraints/ui/RunCard';
import './LiveRuns.css';

const DEPTHS = [10, 30, 120] as const;

interface LiveRunsProps {
  document: ConstraintsDoc;
  scenario?: string;
  blocked: boolean;
  onLoadConditions?: (document: ConstraintsDoc) => void;
}

interface CaseDraft {
  operation: string;
  well?: string;
  date_from?: string;
  date_to?: string;
  control_step_from?: number;
  control_step_to?: number;
  section?: string;
  year?: number;
  before?: number;
  after?: number;
  unit?: string;
  constraints: ConstraintsDoc;
  base_constraints: ConstraintsDoc;
}

interface AlternativeDraft {
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

export const LiveRuns = ({ document, scenario = 'base', blocked, onLoadConditions }: LiveRunsProps) => {
  const { lang, t } = useFallbackI18n();
  const [request, setRequest] = useState('');
  const [draft, setDraft] = useState<CaseDraft | null>(null);
  const [draftError, setDraftError] = useState('');
  const [drafting, setDrafting] = useState(false);
  const [draftRequestId, setDraftRequestId] = useState('');
  const [alternativeSourceRun, setAlternativeSourceRun] = useState('');
  const [alternativeWell, setAlternativeWell] = useState('');
  const [alternativeStep, setAlternativeStep] = useState('');
  const [alternativeTarget, setAlternativeTarget] = useState('');
  const [alternativeDraft, setAlternativeDraft] = useState<AlternativeDraft | null>(null);
  const [alternativeRequestId, setAlternativeRequestId] = useState('');
  const [alternativeError, setAlternativeError] = useState('');
  const [alternativeDrafting, setAlternativeDrafting] = useState(false);
  useEffect(() => setDraft(null), [document, scenario]);
  const { runs, available, busy, error, budget, setBudget, start, startAlternative, cancel } = useLiveRuns({
    document,
    startFailed: t('runs.startFailed'),
    serverDown: t('runs.serverDown')
  });

  const createAlternativeDraft = async (): Promise<void> => {
    setAlternativeDrafting(true);
    setAlternativeDraft(null);
    setAlternativeError('');
    try {
      const response = await fetch('/api/cases/alternative', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          source_run_id: alternativeSourceRun.trim(),
          well: alternativeWell.trim(),
          control_step: Number(alternativeStep),
          target_m3_per_day: Number(alternativeTarget)
        })
      });
      const result = (await response.json()) as AlternativeDraft & { error?: string };
      if (!response.ok) throw new Error(result.error ?? t('runs.alternativeFailed'));
      setAlternativeDraft(result);
      setAlternativeRequestId(crypto.randomUUID());
    } catch (failure) {
      setAlternativeError(failure instanceof Error ? failure.message : t('runs.alternativeFailed'));
    } finally {
      setAlternativeDrafting(false);
    }
  };

  const confirmAlternative = (): void => {
    if (alternativeDraft === null) return;
    const request: AlternativeRequest = {
      request_id: alternativeRequestId,
      source_run_id: alternativeDraft.source_run_id,
      well: alternativeDraft.action.well,
      control_step: alternativeDraft.action.from_step,
      target_m3_per_day: alternativeDraft.action.alternative_target_m3_per_day,
      source_manifest_hash: alternativeDraft.source_manifest_hash,
      source_economics_hash: alternativeDraft.source_economics_hash,
      source_schedule_hash: alternativeDraft.source_schedule_hash,
      alternative_schedule_hash: alternativeDraft.alternative_schedule_hash,
      constraints_hash: alternativeDraft.constraints_hash
    };
    void startAlternative(request);
    setAlternativeDraft(null);
  };

  const createDraft = async (): Promise<void> => {
    setDrafting(true);
    setDraft(null);
    setDraftError('');
    try {
      const response = await fetch('/api/cases/draft', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ request, constraints: document, scenario })
      });
      const result = (await response.json()) as CaseDraft & { error?: string };
      if (!response.ok) throw new Error(result.error ?? t('runs.draftFailed'));
      setDraft({ ...result, base_constraints: document });
      setDraftRequestId(crypto.randomUUID());
    } catch (failure) {
      setDraftError(failure instanceof Error ? failure.message : t('runs.draftFailed'));
    } finally {
      setDrafting(false);
    }
  };

  return (
    <section className="live-runs-panel" aria-label={t('runs.panelLabel')}>
      <h3 className="scenarios-heading">{t('runs.heading')}</h3>
      <p className="scenarios-note">{t('runs.intro')}</p>
      <p className="scenarios-note">{t('runs.fallbackNote')}</p>
      <div className="case-draft-panel">
        <h4>{t('runs.draftHeading')}</h4>
        <p className="scenarios-note">{t('runs.draftIntro')}</p>
        <label>
          {t('runs.draftRequest')}{' '}
          <textarea
            className="scenarios-input"
            value={request}
            maxLength={600}
            rows={3}
            onChange={(event) => { setRequest(event.target.value); setDraft(null); }}
            disabled={drafting || busy}
          />
        </label>
        <button
          className="scenarios-button"
          type="button"
          disabled={request.trim() === '' || drafting || busy || !available || blocked}
          onClick={() => void createDraft()}
        >
          {drafting ? t('runs.draftWorking') : t('runs.draftButton')}
        </button>
        {draftError && <p role="alert" className="scenarios-banner scenarios-banner-error">{draftError}</p>}
        {draft && (
          <div className="case-draft-preview" role="status">
            <strong>{t('runs.draftPreview')}</strong>
            <p>{draft.operation === 'add_well_outage'
              ? t('runs.draftOutage', { well: draft.well ?? '', from: draft.date_from ?? '', to: draft.date_to ?? '' })
              : t('runs.draftLimit', { section: t(`runs.draft.${draft.section ?? ''}`), year: draft.year ?? '', before: draft.before ?? t('runs.draftNone'), after: draft.after ?? '', unit: draft.unit ?? '' })}</p>
            <p>{t('runs.draftConfirmHint')}</p>
            <button
              className="scenarios-button scenarios-button-primary"
              type="button"
              disabled={busy || blocked || !available}
              onClick={() => void start(undefined, draft.constraints, {
                request_id: draftRequestId,
                request,
                scenario,
                base_constraints: draft.base_constraints
              })}
            >
              {t('runs.draftConfirm')}
            </button>
          </div>
        )}
      </div>
      <div className="case-draft-panel">
        <h4>{t('runs.alternativeHeading')}</h4>
        <p className="scenarios-note">{t('runs.alternativeIntro')}</p>
        <label>
          {t('runs.alternativeSource')}{' '}
          <input className="scenarios-input" value={alternativeSourceRun} maxLength={128}
            onChange={(event) => { setAlternativeSourceRun(event.target.value); setAlternativeDraft(null); }}
            disabled={alternativeDrafting || busy} />
        </label>
        <label>
          {t('runs.alternativeWell')}{' '}
          <input className="scenarios-input" value={alternativeWell} maxLength={32}
            onChange={(event) => { setAlternativeWell(event.target.value); setAlternativeDraft(null); }}
            disabled={alternativeDrafting || busy} />
        </label>
        <label>
          {t('runs.alternativeStep')}{' '}
          <input className="scenarios-input" type="number" min={0} step={1} value={alternativeStep}
            onChange={(event) => { setAlternativeStep(event.target.value); setAlternativeDraft(null); }}
            disabled={alternativeDrafting || busy} />
        </label>
        <label>
          {t('runs.alternativeTarget')}{' '}
          <input className="scenarios-input" type="number" min={0.01} max={500} step="any" value={alternativeTarget}
            onChange={(event) => { setAlternativeTarget(event.target.value); setAlternativeDraft(null); }}
            disabled={alternativeDrafting || busy} />
        </label>
        <button className="scenarios-button" type="button"
          disabled={!alternativeSourceRun.trim() || !alternativeWell.trim() || alternativeStep === '' || alternativeTarget === '' || alternativeDrafting || busy || !available || blocked}
          onClick={() => void createAlternativeDraft()}>
          {alternativeDrafting ? t('runs.alternativeWorking') : t('runs.alternativePreview')}
        </button>
        {alternativeError && <p role="alert" className="scenarios-banner scenarios-banner-error">{alternativeError}</p>}
        {alternativeDraft && (
          <div className="case-draft-preview" role="status">
            <strong>{t('runs.alternativePreviewTitle')}</strong>
            <p>{t('runs.alternativeChange', {
              well: alternativeDraft.action.well,
              from: alternativeDraft.action.from_step,
              through: alternativeDraft.action.through_step,
              before: alternativeDraft.action.original_target_m3_per_day,
              after: alternativeDraft.action.alternative_target_m3_per_day
            })}</p>
            <p>{t('runs.alternativeCost', { count: alternativeDraft.additional_opm_evaluations })}</p>
            <p>{t('runs.alternativeBaseline', { value: formatQuantity(lang, alternativeDraft.source_npv_rub, 'rub', 0) })}</p>
            <p>{t('runs.alternativeBoundary')}</p>
            <button className="scenarios-button scenarios-button-primary" type="button"
              disabled={busy || blocked || !available} onClick={confirmAlternative}>
              {t('runs.alternativeConfirm')}
            </button>
          </div>
        )}
      </div>
      <label>
        {t('runs.depthLabel')}{' '}
        <select
          className="scenarios-input"
          value={budget}
          onChange={(event) => setBudget(Number(event.target.value))}
          disabled={busy}
        >
          {DEPTHS.map((depth) => (
            <option key={depth} value={depth}>
              {t(`runs.depth.${depth}`)}
            </option>
          ))}
        </select>
      </label>
      <button
        className="scenarios-button scenarios-button-primary"
        disabled={blocked || busy || !available}
        onClick={() => void start()}
        type="button"
      >
        {t('runs.start')}
      </button>
      {!available && <p role="status">{t('runs.unavailable')}</p>}
      {error !== '' && (
        <p role="alert" className="scenarios-banner scenarios-banner-error">
          {error}
        </p>
      )}
      {runs.length === 0 && <p className="scenarios-note">{t('runs.empty')}</p>}
      {runs.map((run) => (
        <RunCard
          key={run.run_id}
          run={run}
          lang={lang}
          t={t}
          busy={busy}
          onVerify={(runId) => void start(runId)}
          onCancel={(runId) => void cancel(runId)}
          onLoadConditions={onLoadConditions}
          onUseAsAlternativeSource={setAlternativeSourceRun}
        />
      ))}
    </section>
  );
};
