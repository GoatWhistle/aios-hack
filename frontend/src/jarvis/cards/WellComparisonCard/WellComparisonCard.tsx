import { DASH, formatCalendarDate, formatNumber, formatPercent, formatQuantity } from '@/shared/lib/format';
import { useI18n } from '@/shared/i18n/I18nContext';
import { EmptyPayload } from '@/jarvis/cards/EmptyPayload/EmptyPayload';
import { readWellComparison } from '@/jarvis/cards/payloads/wellComparisonPayload';
import { provenanceKindOf } from '@/jarvis/cards/payloads/provenance';
import { wellCodeLabel } from '@/jarvis/cards/lib/wellCodeLabel';
import { translationOrRaw } from '@/jarvis/cards/lib/translationFallback';
import { councilCodeLabel } from '@/jarvis/cards/lib/councilCodeLabel';
import { scenarioLabel } from '@/jarvis/cards/lib/scenarioLabel';
import type { WellComparisonSide } from '@/jarvis/cards/payloads/payloadTypes';
import './WellComparisonCard.css';

const WellComparisonBody = ({ payload }: { payload: NonNullable<ReturnType<typeof readWellComparison>> }) => {
  const { lang, t } = useI18n();
  const metricRows: [string, keyof WellComparisonSide, boolean][] = [
    ['role', 'role', false],
    ['availability', 'availability', false],
    ['operatingStatus', 'operating_status', false],
    ['liquidRate', 'liquid_rate', false],
    ['injectionRate', 'injection_rate', false],
    ['watercut', 'watercut', true],
    ['bhp', 'bhp', false],
    ['setpoint', 'setpoint', false],
    ['wholeHorizonNpv', 'npv_whole_horizon', false]
  ];
  const unitFor = (key: keyof WellComparisonSide): string | null => {
    if (key === 'liquid_rate' || key === 'injection_rate' || key === 'setpoint') return 'm3/day';
    if (key === 'bhp') return 'bar';
    if (key === 'npv_whole_horizon') return 'RUB';
    return null;
  };
  const value = (side: WellComparisonSide, key: keyof WellComparisonSide, percent: boolean) => {
    const raw = side[key];
    const unit = unitFor(key);
    if (typeof raw === 'number') return percent ? formatPercent(lang, raw) : unit === null ? formatNumber(lang, raw, 3) : formatQuantity(lang, raw, unit, 3);
    if (typeof raw !== 'string') return DASH;
    if (key === 'role') return wellCodeLabel(raw, 'role', t);
    if (key === 'availability') return wellCodeLabel(raw, 'availability', t);
    if (key === 'operating_status') return wellCodeLabel(raw, 'status', t);
    return raw;
  };
  const recordedA = payload.decision_evidence.wells[payload.a.well];
  const recordedB = payload.decision_evidence.wells[payload.b.well];
  const quotaEvidence = Object.entries(payload.decision_evidence.wells)
    .filter(([, evidence]) => evidence.recorded === true);
  const fieldLimits = new Map<number, string[]>();
  const groupAllocations = new Map<string, {
    group: string;
    value: number | null;
    wells: string[];
  }>();
  for (const [well, evidence] of quotaEvidence) {
    if (evidence.field_injection_limit_m3_per_day !== null) {
      const sources = fieldLimits.get(evidence.field_injection_limit_m3_per_day) ?? [];
      sources.push(well);
      fieldLimits.set(evidence.field_injection_limit_m3_per_day, sources);
    }
    for (const allocation of evidence.group_allocations) {
      const key = `${allocation.group_id}:${allocation.injection_m3_per_day ?? 'unknown'}`;
      const row = groupAllocations.get(key) ?? {
        group: allocation.group_id,
        value: allocation.injection_m3_per_day,
        wells: []
      };
      row.wells.push(well);
      groupAllocations.set(key, row);
    }
  }

  return (
    <div className="jarvis-well-comparison">
      <p className="jarvis-well-comparison-context">{scenarioLabel(payload.scenario, t)} · {t('jarvis-cards.step')} {payload.step} · {formatCalendarDate(lang, payload.date)}</p>
      <div className="jarvis-well-comparison-columns">
        {[payload.a, payload.b].map((side) => (
          <section className="jarvis-well-comparison-side" key={side.well}>
            <h4>{t('jarvis-cards.well')} {side.well}</h4>
            {metricRows.map(([label, key, percent]) => (
              <p key={key}><span>{t(`jarvis-cards.${label}`)}</span><strong>{value(side, key, percent)}</strong></p>
            ))}
          </section>
        ))}
      </div>
      <section className="jarvis-well-comparison-note">
        <strong>{t('jarvis-cards.deltaBMinusA')}</strong>
        {metricRows.filter(([, key]) => ['liquid_rate', 'injection_rate', 'watercut', 'bhp', 'setpoint'].includes(key)).map(([label, key, percent]) => {
          const delta = payload.deltas_b_minus_a[key];
          const unit = unitFor(key);
          return <p key={key}>{t(`jarvis-cards.${label}`)}: {typeof delta === 'number' ? (percent ? formatPercent(lang, delta) : unit === null ? formatNumber(lang, delta, 3) : formatQuantity(lang, delta, unit, 3)) : DASH}</p>;
        })}
        <p>{t('jarvis-cards.wholeHorizonNpv')}: {typeof payload.deltas_b_minus_a.npv_whole_horizon === 'number' ? formatQuantity(lang, payload.deltas_b_minus_a.npv_whole_horizon, 'RUB') : DASH}</p>
        <p title={payload.npv_provenance}>{t('jarvis-cards.wellNpvSource', { source: provenanceKindOf(payload.npv_provenance) === 'unknown' ? payload.npv_provenance : t(`jarvis-cards.provenanceKind.${provenanceKindOf(payload.npv_provenance)}`) })}{payload.npv_source_run_id ? ` · ${payload.npv_source_run_id}` : ''}</p>
      </section>
      <section className="jarvis-well-comparison-note">
        <strong>{t('jarvis-cards.wellConstraints')}</strong>
        {payload.decision_evidence.source_alignment === 'different-response' ? (
          <p role="note">{t('jarvis-cards.wellComparisonDifferentSource', {
            stateRun: payload.decision_evidence.state_source_run_id ?? '—',
            decisionRun: payload.decision_evidence.run_id ?? '—'
          })}</p>
        ) : null}
        {payload.decision_evidence.run_id !== null && payload.decision_evidence.source_alignment === 'unverified' ? (
          <p role="note">{t('jarvis-cards.wellComparisonSourceUnverified', {
            stateRun: payload.decision_evidence.state_source_run_id ?? '—',
            decisionRun: payload.decision_evidence.run_id
          })}</p>
        ) : null}
        <p>{translationOrRaw(
          `jarvis-cards.wellConstraintsStatus.${payload.decision_evidence.well_constraints.status}`,
          payload.decision_evidence.well_constraints.status,
          t
        )}</p>
        {[payload.a, payload.b].map((side) => {
          const outages = payload.decision_evidence.well_constraints.outages[side.well] ?? [];
          return <p key={`outage-${side.well}`}>{t('jarvis-cards.well')} {side.well}: {outages.length
            ? t('jarvis-cards.wellOutageAtStep', { steps: outages.map((item) => `${item.control_step_from}–${item.control_step_to}`).join(', ') })
            : t('jarvis-cards.noWellOutageAtStep')}</p>;
        })}
        {payload.direct_connection ? (
          <p title={payload.direct_connection.provenance}>{t('jarvis-cards.measuredDirectLink', { weight: payload.direct_connection.weight === null ? DASH : formatNumber(lang, payload.direct_connection.weight, 3) })} · {provenanceKindOf(payload.direct_connection.provenance) === 'unknown' ? payload.direct_connection.provenance : t(`jarvis-cards.provenanceKind.${provenanceKindOf(payload.direct_connection.provenance)}`)}</p>
        ) : (
          <p>{t('jarvis-cards.noMeasuredDirectLink')}</p>
        )}
        {fieldLimits.size === 0 && groupAllocations.size === 0 ? null : (
          <div className="jarvis-well-comparison-quotas">
            <strong>{t('jarvis-cards.recordedQuotas')}</strong>
            {[...fieldLimits].map(([limit, wells]) => (
              <p key={`field-limit-${limit}`}>
                {t('jarvis-cards.fieldInjectionLimit')}: {formatQuantity(lang, limit, 'm3/day', 3)}
                {' · '}{t('jarvis-cards.quotaEvidenceWells', { wells: wells.join(', ') })}
              </p>
            ))}
            {[...groupAllocations.values()].map((allocation) => (
              <p key={`group-${allocation.group}-${allocation.value ?? 'unknown'}`}>
                {allocation.group}: {allocation.value === null ? DASH : formatQuantity(lang, allocation.value, 'm3/day', 3)}
                {' · '}{t('jarvis-cards.quotaEvidenceWells', { wells: allocation.wells.join(', ') })}
              </p>
            ))}
          </div>
        )}
        {payload.decision_evidence.run_id ? <strong>{t('jarvis-cards.recordedEvaluation', { run: payload.decision_evidence.run_id })}</strong> : null}
        {[{ side: payload.a, evidence: recordedA }, { side: payload.b, evidence: recordedB }].map(({ side, evidence }) => (
          <div key={side.well}>
            <p>{t('jarvis-cards.well')} {side.well}: {evidence?.recorded === true
              ? t('jarvis-cards.evidenceRecorded')
              : evidence?.recorded === false
                ? t('jarvis-cards.evidenceNotRecorded')
                : t(payload.decision_evidence.status === 'run-evidence-unavailable'
                  ? 'jarvis-cards.evidenceUnavailable'
                  : 'jarvis-cards.evidenceNotChecked')}</p>
            {evidence?.recorded === true ? (
              <>
                <p>{t('jarvis-cards.recordedRules')}: {evidence.rule_count} · {t('jarvis-cards.finalCommands')}: {evidence.final_event_count}</p>
                {evidence.rules.map((rule, index) => (
                  <p key={`${rule.level}-${rule.agent}-${rule.rule}-${index}`}><code>
                    {translationOrRaw(`jarvis-cards.ruleFactLevel.${rule.level}`, rule.level, t)}/{councilCodeLabel('agent', rule.agent, t)} · {translationOrRaw(`jarvis-cards.ruleFactName.${rule.rule}`, rule.rule, t)} → {councilCodeLabel('action', rule.decision, t)}
                  </code></p>
                ))}
              </>
            ) : null}
          </div>
        ))}
        <p>{t('jarvis-cards.pairwisePreferenceNotRecorded')}</p>
        <small>{t('jarvis-cards.stateComparisonOnly')}</small>
      </section>
    </div>
  );
};

export const WellComparisonCard = ({ payload }: { payload: unknown }) => {
  const parsed = readWellComparison(payload);
  return parsed ? <WellComparisonBody payload={parsed} /> : <EmptyPayload />;
};
