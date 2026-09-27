import { useState } from 'react';
import { DASH, formatNumber, formatQuantity } from '@/shared/lib/format';
import { useI18n } from '@/shared/i18n/I18nContext';
import { readCompare } from '@/jarvis/cards/payloads';
import type { CompareConstraints, CompareStatus } from '@/jarvis/cards/payloads/payloadTypes';
import { runStatusLabel } from '@/jarvis/cards/lib/runStatusLabel';
import { translationOrRaw } from '@/jarvis/cards/lib/translationFallback';
import { opmStatusLabel } from '@/jarvis/cards/lib/opmStatusLabel';
import { EmptyPayload } from '@/jarvis/cards/EmptyPayload/EmptyPayload';
import { Markdown } from '@/jarvis/markdown/Markdown/Markdown';
import type { ConsoleAction } from '@/jarvis/actions/lib/consoleAction';
import './CompareCard.css';

const flagKeys = (status: CompareStatus): { key: string; on: boolean }[] => {
  const collected: { key: string; on: boolean }[] = [];
  if (status.sound !== null) {
    collected.push({ key: 'jarvis-cards.compareSound', on: status.sound });
  }
  if (status.converged !== null) {
    collected.push({ key: 'jarvis-cards.compareConverged', on: status.converged });
  }
  if (status.self_consistent !== null) {
    collected.push({ key: 'jarvis-cards.compareConsistent', on: status.self_consistent });
  }
  if (status.has_submission !== null) {
    collected.push({ key: 'jarvis-cards.compareSubmitted', on: status.has_submission });
  }
  return collected;
};

const constraintCount = (constraints: CompareConstraints): string =>
  constraints.total === null ? DASH : String(constraints.total);

const constraintGroupLabel = (key: string, t: ReturnType<typeof useI18n>['t']): string => {
  const translationKey = `jarvis-cards.compareConstraintGroup.${key}`;
  const translated = t(translationKey);
  return translated === translationKey ? key : translated;
};

const economicLineLabel = (key: string, t: ReturnType<typeof useI18n>['t']): string => {
  const translationKey = `jarvis-cards.economicLine.${key}`;
  const translated = t(translationKey);
  return translated === translationKey ? key : translated;
};

const reasonLabel = (
  reason: string,
  category: 'economic' | 'production',
  t: ReturnType<typeof useI18n>['t']
): string => {
  const known: Record<string, string> = category === 'economic' ? {
    'one or both runs have no recorded economics/npv-table.json': 'missingTable',
    'the recorded NPV table has no annual line items': 'noAnnualLines'
  } : {
    'one or both runs have no observation/<schedule_hash>/response.json': 'missingResponse',
    'an observation response has no interval_response rows': 'missingIntervalRows',
    'the OPM responses share no well/control_step rows': 'noSharedWellStep'
  };
  const key = known[reason];
  return key === undefined ? reason : translationOrRaw(`jarvis-cards.compareReason.${category}.${key}`, reason, t);
};

const missingWellBreakdownLabel = (reason: string, t: ReturnType<typeof useI18n>['t']): string => {
  const match = /^no-comparison: run (.+) has no comparison\.json file, so the breakdown of the difference by well is unknown$/.exec(reason);
  return match === null ? reason : t('jarvis-cards.compareReason.missingWellBreakdown', { run: match[1] });
};

const comparabilityNote = (
  comparability: NonNullable<ReturnType<typeof readCompare>>['comparability'],
  t: ReturnType<typeof useI18n>['t']
): string => {
  if (comparability === null || comparability.missing_fields === null || comparability.mismatched_fields === null) {
    return comparability?.note ?? '';
  }
  const fields = (items: string[]) => items.map((field) => translationOrRaw(`jarvis-cards.compareField.${field}`, field, t)).join(', ');
  if (comparability.mismatched_fields.length > 0) {
    return t('jarvis-cards.compareMismatchNote', { fields: fields(comparability.mismatched_fields) });
  }
  if (comparability.missing_fields.length > 0) {
    return t('jarvis-cards.compareMissingNote', { fields: fields(comparability.missing_fields) });
  }
  return t('jarvis-cards.compareMatchedNote');
};

export const CompareCard = ({ payload, action, onOpen }: { payload: unknown; action?: ConsoleAction; onOpen?: (action: ConsoleAction) => void }) => {
  const { lang, t } = useI18n();
  const [copied, setCopied] = useState(false);
  const compare = readCompare(payload);
  if (compare === null) {
    return <EmptyPayload />;
  }
  const delta = compare.delta_npv;
  const copyConclusion = async () => {
    if (compare.conclusion_markdown === null) return;
    try {
      if (navigator.clipboard?.writeText) await navigator.clipboard.writeText(compare.conclusion_markdown);
      else {
        const field = document.createElement('textarea');
        field.value = compare.conclusion_markdown;
        field.style.position = 'fixed';
        field.style.opacity = '0';
        document.body.appendChild(field);
        field.select();
        const success = document.execCommand('copy');
        field.remove();
        if (!success) throw new Error('clipboard unavailable');
      }
      setCopied(true);
    } catch {
      setCopied(false);
    }
  };

  return (
    <div className="jarvis-compare">
      <div className="jarvis-compare-sides">
        {[compare.a, compare.b].map((side) => (
          <div className="jarvis-compare-side" key={side.id}>
            <p className="jarvis-compare-id">{side.id}</p>
            <p className="jarvis-compare-npv">
              {side.npv === null ? DASH : formatQuantity(lang, side.npv, 'RUB')}
            </p>
            <p className="jarvis-compare-meta">{side.npv_basis === null
              ? t('jarvis-cards.compareNpvSourceUnknown')
              : translationOrRaw(`jarvis-cards.compareNpvBasis_${side.npv_basis}`, side.npv_basis, t)}</p>
            <p className="jarvis-compare-status">
              {side.status.status === null ? opmStatusLabel(side.status.opm_status, t) : runStatusLabel(side.status.status, t)}
            </p>
            <ul className="jarvis-compare-flags">
              {flagKeys(side.status).map((flag) => (
                <li key={flag.key} data-on={flag.on ? 'true' : 'false'}>
                  {t(flag.key)}
                </li>
              ))}
            </ul>
            {side.status.ood_score === null ? null : (
              <p className="jarvis-compare-ood">
                {t('jarvis-cards.compareOod')}: {formatNumber(lang, side.status.ood_score, 2)}
                {side.status.ood_threshold === null
                  ? ''
                  : ` / ${formatNumber(lang, side.status.ood_threshold, 2)}`}
              </p>
            )}
            <p className="jarvis-compare-meta">
              <span>
                {t('jarvis-cards.compareConstraints')}: {constraintCount(side.constraints)}
              </span>
            </p>
            {side.constraints.groups.length === 0 ? null : (
              <ul className="jarvis-compare-groups">
                {side.constraints.groups
                  .filter((group) => group.count > 0)
                  .map((group) => (
                    <li key={group.key}>
                      <span>{constraintGroupLabel(group.key, t)}</span>
                      <span>{t('jarvis-cards.compareConstraintGroupCount', { count: String(group.count) })}</span>
                    </li>
                  ))}
              </ul>
            )}
          </div>
        ))}
      </div>
      <p className="jarvis-compare-delta" data-sign={(delta ?? 0) >= 0 ? 'up' : 'down'}>
        <span className="jarvis-compare-delta-label">{t('jarvis-cards.compareDelta')}</span>
        {delta === null ? DASH : formatQuantity(lang, delta, 'RUB')}
      </p>
      {delta === null ? <p className="jarvis-compare-reason">{t('jarvis-cards.compareNpvDeltaUnavailable')}</p> : null}
      {compare.comparability === null ? null : (
        <p className="jarvis-compare-reason" data-comparable={compare.comparability.status === 'comparable' ? 'true' : 'false'}>
          {comparabilityNote(compare.comparability, t)}
        </p>
      )}
      {compare.economic_breakdown.deltas_b_minus_a === null ? (
        <p className="jarvis-compare-reason">{compare.economic_breakdown.reason === null
          ? t('jarvis-cards.economicBreakdownMissing')
          : reasonLabel(compare.economic_breakdown.reason, 'economic', t)}</p>
      ) : (
        <div className="jarvis-compare-groups">
          <p>{t('jarvis-cards.economicBreakdown')}</p>
          <ul className="jarvis-compare-well-list">
            {Object.entries(compare.economic_breakdown.deltas_b_minus_a)
              .filter(([key]) => key !== 'df')
              .map(([key, value]) => (
                <li key={key}><span>{economicLineLabel(key, t)}</span><span>{formatQuantity(lang, value, 'RUB')}</span></li>
              ))}
          </ul>
        </div>
      )}
      <section className="jarvis-compare-groups">
        <p>{t('jarvis-cards.productionInjection')}</p>
        {!compare.production_injection.recorded || compare.production_injection.totals_delta_b_minus_a === null ? (
          <p className="jarvis-compare-reason">{compare.production_injection.reason === null
            ? t('jarvis-cards.productionInjectionMissing')
            : reasonLabel(compare.production_injection.reason, 'production', t)}</p>
        ) : (
          <>
            <p className="jarvis-compare-reason">{t('jarvis-cards.productionInjectionScope', {
              matched: compare.production_injection.matched_rows,
              unmatched: compare.production_injection.unmatched_rows ?? 0
            })}</p>
            <ul className="jarvis-compare-well-list">
              <li><span>{t('jarvis-cards.oilMassDelta')}</span><span>{formatQuantity(lang, compare.production_injection.totals_delta_b_minus_a.oil_mass_delta, 'kg')}</span></li>
              <li><span>{t('jarvis-cards.injectionVolumeDelta')}</span><span>{formatQuantity(lang, compare.production_injection.totals_delta_b_minus_a.injection_volume_delta, 'm3')}</span></li>
            </ul>
            {compare.production_injection.top_diff_wells_steps.length === 0 ? null : (
              <ol className="jarvis-compare-well-list">
                {compare.production_injection.top_diff_wells_steps.map((row) => (
                  <li key={`${row.well}-${row.control_step}`}>
                    <span>{row.well} · {t('jarvis-cards.step')} {row.control_step}: {t('jarvis-cards.oilMassDelta')} {formatQuantity(lang, row.oil_mass_delta_b_minus_a, 'kg')}, {t('jarvis-cards.injectionVolumeDelta')} {formatQuantity(lang, row.injection_volume_delta_b_minus_a, 'm3')}</span>
                    {onOpen === undefined ? null : <button type="button" onClick={() => onOpen({
                      workspace: 'field', view: 'projection', run_id: action?.run_id ?? compare.b.id,
                      scenario: action?.scenario,
                      well: row.well, step: row.control_step
                    })}>{t('jarvis-cards.openViolationLocation')}</button>}
                  </li>
                ))}
              </ol>
            )}
          </>
        )}
      </section>
      {compare.top_diff_wells.length === 0 ? (
        compare.comparison_reason === null ? null : (
          <p className="jarvis-compare-reason">{missingWellBreakdownLabel(compare.comparison_reason, t)}</p>
        )
      ) : (
        <div className="jarvis-compare-wells">
          <p className="jarvis-compare-wells-label">{t('jarvis-cards.compareTopWells')}</p>
          <ol className="jarvis-compare-well-list">
            {compare.top_diff_wells.map((row) => (
              <li key={row.well} data-sign={row.delta >= 0 ? 'up' : 'down'}>
                <span className="jarvis-compare-well">{row.well}</span>
                <span className="jarvis-compare-well-delta">
                  {formatQuantity(lang, row.delta, 'RUB')}
                </span>
              </li>
            ))}
          </ol>
        </div>
      )}
      {compare.conclusion_markdown === null ? null : (
        <details className="jarvis-compare-conclusion">
          <summary>{t('jarvis-cards.compareConclusion')}</summary>
          <div className="jarvis-compare-conclusion-actions">
            <button type="button" onClick={() => { void copyConclusion(); }}>{copied ? t('jarvis-cards.copied') : t('jarvis-cards.copy')}</button>
            <button type="button" onClick={() => {
              const blob = new Blob([compare.conclusion_markdown ?? ''], { type: 'text/markdown;charset=utf-8' });
              const url = URL.createObjectURL(blob);
              const link = document.createElement('a');
              link.href = url;
              link.download = `comparison-${compare.a.id}-vs-${compare.b.id}.md`;
              link.click();
              URL.revokeObjectURL(url);
            }}>{t('jarvis-cards.downloadMarkdown')}</button>
          </div>
          <Markdown source={compare.conclusion_markdown} />
        </details>
      )}
    </div>
  );
};
