import { DASH, formatCalendarDate, formatNumber, formatQuantity, formatTimestamp } from '@/shared/lib/format';
import { useI18n } from '@/shared/i18n/I18nContext';
import { readStatusBoard } from '@/jarvis/cards/payloads';
import { runStatusLabel } from '@/jarvis/cards/lib/runStatusLabel';
import { violationKindLabel } from '@/jarvis/cards/lib/violationKindLabel';
import { provenanceKindOf } from '@/jarvis/cards/payloads/provenance';
import { diagnosticPatternLabel } from '@/jarvis/cards/lib/diagnosticPatternLabel';
import { violationDetailLabel } from '@/jarvis/cards/lib/violationDetailLabel';
import { scenarioLabel } from '@/jarvis/cards/lib/scenarioLabel';
import { EmptyPayload } from '@/jarvis/cards/EmptyPayload/EmptyPayload';
import type { ConsoleAction } from '@/jarvis/actions/lib/consoleAction';
import { useEffect, useState } from 'react';
import './StatusBoardCard.css';

const championReasonLabel = (reason: string, t: ReturnType<typeof useI18n>['t']): string => {
  const missing = /^there is no champion file (.+): no pinned best OPM run is recorded$/.exec(reason);
  return missing === null ? reason : t('jarvis-cards.boardChampionMissing', { path: missing[1] });
};

const lastRunReasonLabel = (reason: string, t: ReturnType<typeof useI18n>['t']): string => {
  const noRun = /^the runs directory holds no run with a manifest: (.+); no calculation has been made yet$/.exec(reason);
  if (noRun !== null) return t('jarvis-cards.boardNoRunManifest', { path: noRun[1] });
  if (reason === 'the runs directory was not found: point at it with environment variable AIOS_JARVIS_RUNS or run from the repository root that holds out/runs') {
    return t('jarvis-cards.boardRunsDirectoryMissing');
  }
  return reason;
};

const STALE_AFTER_MS = 10 * 60 * 1000;

export const StatusBoardCard = ({ payload, onOpen, loading = false }: { payload: unknown; onOpen: (action: ConsoleAction) => void; loading?: boolean }) => {
  const { lang, t } = useI18n();
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 30_000);
    return () => window.clearInterval(timer);
  }, []);
  const board = readStatusBoard(payload);
  if (board === null) {
    return <EmptyPayload />;
  }
  const { champion, last_run: last } = board;
  const generatedAt = board.generated_at === null ? null : new Date(board.generated_at);
  const generatedAtValid = generatedAt !== null && Number.isFinite(generatedAt.getTime());
  const stale = generatedAtValid && now - generatedAt.getTime() > STALE_AFTER_MS;

  return (
    <div className="jarvis-board">
      {loading ? <p className="jarvis-board-loading" role="status" aria-live="polite">{t('jarvis-cards.briefingLoading')}</p> : null}
      <p className="jarvis-board-freshness" data-stale={stale ? 'true' : 'false'}>
        {generatedAtValid
          ? `${t('jarvis-cards.briefingGenerated')}: ${formatTimestamp(lang, board.generated_at ?? '')}`
          : t('jarvis-cards.briefingTimeUnavailable')}
        {stale ? ` · ${t('jarvis-cards.briefingStale')}` : ''}
      </p>
      <section className="jarvis-board-block">
        <p className="jarvis-board-label">{t('jarvis-cards.boardChampion')}</p>
        {champion.recorded ? (
          <>
            <p className="jarvis-board-value">
              {champion.npv === null ? DASH : formatQuantity(lang, champion.npv, 'RUB')}
            </p>
            <p className="jarvis-board-flags">
              <span data-on={champion.sound === true ? 'true' : 'false'}>
                {t('jarvis-cards.compareSound')}
              </span>
              {champion.ood === null ? null : (
                <span data-on="true">
                  {t('jarvis-cards.compareOod')} {formatNumber(lang, champion.ood, 2)}
                </span>
              )}
            </p>
          </>
        ) : (
          <p className="jarvis-board-missing">{champion.reason === null
            ? t('jarvis-cards.boardNoRun')
            : championReasonLabel(champion.reason, t)}</p>
        )}
      </section>
      <section className="jarvis-board-block">
        <p className="jarvis-board-label">{t('jarvis-cards.boardLastRun')}</p>
        {last.recorded ? (
          <>
            <p className="jarvis-board-run">{last.run_id ?? DASH}</p>
            <p className="jarvis-board-value">
              {last.verified_npv === null
                ? last.predicted_npv === null
                  ? DASH
                  : formatQuantity(lang, last.predicted_npv, 'RUB')
                : formatQuantity(lang, last.verified_npv, 'RUB')}
            </p>
            <p className="jarvis-board-status">{runStatusLabel(last.status, t)}</p>
          </>
        ) : (
          <p className="jarvis-board-missing">{last.reason === null
            ? t('jarvis-cards.boardNoRun')
            : lastRunReasonLabel(last.reason, t)}</p>
        )}
      </section>
      <section className="jarvis-board-block">
        <p className="jarvis-board-label">{t('jarvis-cards.boardNow')}</p>
        <p className="jarvis-board-now">
          {scenarioLabel(board.scenario, t)} · {t('jarvis-screen.contextStep')} {board.step}
          {board.date === null ? '' : ` · ${formatCalendarDate(lang, board.date)}`}
        </p>
        <p className="jarvis-board-data" title={board.data}>
          {t('jarvis-cards.boardDataSource')}: {provenanceKindOf(board.data) === 'unknown'
            ? board.data
            : t(`jarvis-cards.provenanceKind.${provenanceKindOf(board.data)}`)}
        </p>
      </section>
      {board.alerts.length === 0 && board.diagnostics.recorded ? <p>{t('jarvis-cards.noFindingsRecorded')}</p> : null}
      {board.alerts.length === 0 ? null : (
        <section className="jarvis-board-block">
          <p className="jarvis-board-label">{t('jarvis-cards.boardAlerts')}</p>
          <ul className="jarvis-board-alerts">
            {board.alerts.map((alert, index) => (
              <li key={`${alert.pattern ?? index}`} data-severity={alert.severity ?? 'info'}>
                <span title={alert.pattern ?? undefined}>{diagnosticPatternLabel(alert.pattern, alert.name, t)}</span>
                <span className="jarvis-board-alert-well">{alert.well ?? DASH}</span>
                {alert.step === null ? null : (
                  <span className="jarvis-board-alert-step">{alert.step}</span>
                )}
                {alert.date === null ? <span>{t('jarvis-cards.noDateRecorded')}</span> : <span>{formatCalendarDate(lang, alert.date)}</span>}
                {alert.window === null ? null : <span>{t('jarvis-cards.interval')} {alert.window[0]}–{alert.window[1]}</span>}
                {alert.source === null ? null : (
                  <small title={alert.source}>
                    {provenanceKindOf(alert.source) === 'unknown'
                      ? alert.source
                      : t(`jarvis-cards.provenanceKind.${provenanceKindOf(alert.source)}`)}
                  </small>
                )}
                {alert.well === null ? null : (
                  <span className="jarvis-board-alert-actions">
                    <button type="button" onClick={() => onOpen({
                      workspace: 'decisions', view: 'rules', scenario: board.scenario,
                      ...(alert.step === null ? {} : { step: alert.step }), well: alert.well
                    })}>{t('jarvis-cards.explain')}</button>
                    <button type="button" onClick={() => onOpen({
                      workspace: 'field', view: 'projection', scenario: board.scenario,
                      ...(alert.step === null ? {} : { step: alert.step }), well: alert.well
                    })}>{t('jarvis-cards.openWell')}</button>
                  </span>
                )}
              </li>
            ))}
          </ul>
        </section>
      )}
      {!board.diagnostics.recorded ? <p className="jarvis-board-missing">{board.diagnostics.reason ?? t('jarvis-cards.diagnosticsUnavailable')}</p> : null}
      <section className="jarvis-board-block">
        <p className="jarvis-board-label">{t('jarvis-cards.recordedViolations')}</p>
        {!board.violations.recorded ? <p className="jarvis-board-missing">{board.violations.reason ?? t('jarvis-cards.violationLocationsMissing')}</p> : board.violations.rows.length === 0 ? <p>{t('jarvis-cards.noRecordedViolations')}</p> : (
          <ul className="jarvis-board-alerts">
            {board.violations.rows.map((row, index) => (
              <li key={`${row.kind}-${row.control_step}-${row.well}-${index}`} data-severity={row.blocking ? 'high' : 'warning'}>
                <span>{violationKindLabel(row.kind, t)}{row.blocking ? ` · ${t('jarvis-cards.blocking')}` : ''}</span>
                <span>{violationDetailLabel(row.kind, row.detail, lang, t)}</span>
                <span>{row.well === null ? (row.region === null ? t('jarvis-cards.fieldLevel') : `${t('jarvis-cards.region')} ${row.region}`) : `${t('jarvis-cards.well')} ${row.well}`}{row.control_step === null ? '' : ` · ${t('jarvis-screen.contextStep')} ${row.control_step}`}</span>
                {board.violations.run_id ? <small>{`runs/${board.violations.run_id}/validation/violations.json`}</small> : null}
                {row.well === null && row.control_step === null ? null : (
                  <button type="button" onClick={() => onOpen({
                    run_id: board.violations.run_id,
                    workspace: 'field', view: 'projection',
                    ...(row.control_step === null ? {} : { step: row.control_step }),
                    ...(row.well === null ? {} : { well: row.well })
                  })}>{t('jarvis-cards.showViolation')}</button>
                )}
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
};
