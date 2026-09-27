import { useState } from 'react';
import { DASH, formatCalendarDate, formatNumber, formatQuantity } from '@/shared/lib/format';
import { useI18n } from '@/shared/i18n/I18nContext';
import { readRun } from '@/jarvis/cards/payloads';
import { runStatusLabel } from '@/jarvis/cards/lib/runStatusLabel';
import { violationKindLabel } from '@/jarvis/cards/lib/violationKindLabel';
import { violationDetailLabel } from '@/jarvis/cards/lib/violationDetailLabel';
import { EmptyPayload } from '@/jarvis/cards/EmptyPayload/EmptyPayload';
import { Markdown } from '@/jarvis/markdown/Markdown/Markdown';
import './RunCard.css';

export const RunCard = ({ payload }: { payload: unknown }) => {
  const { lang, t } = useI18n();
  const [copied, setCopied] = useState(false);
  const [copyFailed, setCopyFailed] = useState(false);
  const run = readRun(payload);
  if (run === null) {
    return <EmptyPayload />;
  }

  const violationDetail = (kind: string, detail: string): string => {
    if (kind !== 'dynamic-violations') return detail;
    const counts = /^(\d+) total; (\d+) blocking$/.exec(detail);
    return counts === null
      ? detail
      : t('jarvis-cards.dynamicViolationSummary', {
        total: formatNumber(lang, Number(counts[1]), 0),
        blocking: formatNumber(lang, Number(counts[2]), 0)
      });
  };

  const copyConclusion = async () => {
    if (run.conclusion_markdown === null) return;
    try {
      if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(run.conclusion_markdown);
      } else {
        const field = document.createElement('textarea');
        field.value = run.conclusion_markdown;
        field.style.position = 'fixed';
        field.style.opacity = '0';
        document.body.appendChild(field);
        field.select();
        const copiedText = document.execCommand('copy');
        field.remove();
        if (!copiedText) throw new Error('clipboard is unavailable');
      }
      setCopied(true);
      setCopyFailed(false);
    } catch {
      setCopied(false);
      setCopyFailed(true);
    }
  };

  return (
    <div className="jarvis-run">
      <p className="jarvis-run-id">{run.run_id}</p>
      <p className="jarvis-run-manifest-date">
        {t('jarvis-cards.runManifestModified')}: {run.ts === ''
          ? t('jarvis-cards.noDateRecorded')
          : <time dateTime={run.ts}>{formatCalendarDate(lang, run.ts)}</time>}
      </p>
      {run.availability_note === null ? null : (
        <p className="jarvis-run-availability">{run.availability_note}</p>
      )}
      <dl className="jarvis-run-facts">
        <div>
          <dt>{t('jarvis-cards.runStatus')}</dt>
          <dd>{runStatusLabel(run.status, t)}</dd>
        </div>
        <div>
          <dt>{t('jarvis-cards.runPredicted')}</dt>
          <dd>
            {run.predicted_npv === null ? DASH : formatQuantity(lang, run.predicted_npv, 'RUB')}
          </dd>
        </div>
        <div>
          <dt>{t('jarvis-cards.runVerified')}</dt>
          <dd>{run.verified_npv === null ? DASH : formatQuantity(lang, run.verified_npv, 'RUB')}</dd>
        </div>
        <div>
          <dt>{t('jarvis-cards.compareSound')}</dt>
          <dd>{run.sound === null ? DASH : run.sound ? t('jarvis-cards.yes') : t('jarvis-cards.no')}</dd>
        </div>
        <div>
          <dt>{t('jarvis-cards.runSubmission')}</dt>
          <dd>{run.has_submission ? t('jarvis-cards.yes') : t('jarvis-cards.no')}</dd>
        </div>
      </dl>
      {run.physics === null ? null : (
        <p className="jarvis-run-physics" data-ok={run.physics.admissible === true ? 'true' : 'false'}>
          {t('jarvis-cards.physicsAdmissible')}:{' '}
          {run.physics.admissible === null
            ? DASH
            : run.physics.admissible
              ? t('jarvis-cards.yes')
              : t('jarvis-cards.no')}
          {run.physics.blocking === null
            ? ''
            : ` · ${t('jarvis-cards.physicsBlocking')} ${run.physics.blocking}`}
          {run.physics.warnings === null
            ? ''
            : ` · ${t('jarvis-cards.physicsWarnings')} ${run.physics.warnings}`}
        </p>
      )}
      {run.violations.length === 0 ? null : (
        <ul className="jarvis-run-violations">
          {run.violations.map((row, index) => (
            <li key={`${row.kind}-${index}`}>
              <span className="jarvis-run-violation-kind" title={row.kind}>
                {violationKindLabel(row.kind, t)}
              </span>
              <span>{violationDetailLabel(row.kind, violationDetail(row.kind, row.detail), lang, t)}</span>
            </li>
          ))}
        </ul>
      )}
      {run.schedule_hash === null ? null : (
        <p className="jarvis-run-hash">{run.schedule_hash}</p>
      )}
      {run.conclusion_markdown === null ? null : (
        <details className="jarvis-run-conclusion">
          <summary>{t('jarvis-cards.runConclusion')}</summary>
          <div className="jarvis-run-conclusion-actions">
            <button type="button" onClick={() => { void copyConclusion(); }}>
              {copied ? t('jarvis-cards.copied') : t('jarvis-cards.copy')}
            </button>
            {copyFailed ? <span role="status">{t('jarvis-cards.copyFailed')}</span> : null}
            <button type="button" onClick={() => {
              const blob = new Blob([run.conclusion_markdown ?? ''], { type: 'text/markdown;charset=utf-8' });
              const url = URL.createObjectURL(blob);
              const link = document.createElement('a');
              link.href = url;
              link.download = `run-${run.run_id}-conclusion.md`;
              link.click();
              URL.revokeObjectURL(url);
            }}>{t('jarvis-cards.downloadMarkdown')}</button>
          </div>
          <Markdown source={run.conclusion_markdown} />
        </details>
      )}
    </div>
  );
};
