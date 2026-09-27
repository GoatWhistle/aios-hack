import type { ConsoleAction } from '@/jarvis/actions/lib/consoleAction';
import { DASH, formatNumber, formatPercent, formatQuantity } from '@/shared/lib/format';
import { useI18n } from '@/shared/i18n/I18nContext';
import { readRunStatus } from '@/jarvis/cards/payloads';
import { runStatusLabel } from '@/jarvis/cards/lib/runStatusLabel';
import { violationKindLabel } from '@/jarvis/cards/lib/violationKindLabel';
import { translationOrRaw } from '@/jarvis/cards/lib/translationFallback';
import { opmStatusLabel } from '@/jarvis/cards/lib/opmStatusLabel';
import { violationDetailLabel } from '@/jarvis/cards/lib/violationDetailLabel';
import { EmptyPayload } from '@/jarvis/cards/EmptyPayload/EmptyPayload';
import './RunStatusCard.css';

const violationValue = (lang: 'ru' | 'en', kind: string, value: number | null): string | null => {
  if (value === null) return null;
  if (['WATERCUT_LIMIT_EXCEEDED', 'TARGET_UNDERSHOOT', 'BHP_LIMITED_WITHOUT_UNDERSHOOT'].includes(kind)) {
    return formatPercent(lang, value);
  }
  if (['BHP_BELOW_PRODUCER_LIMIT', 'BHP_ABOVE_INJECTOR_LIMIT', 'FIELD_PRESSURE_BELOW_FLOOR', 'FIELD_PRESSURE_ABOVE_CEILING', 'REGION_PRESSURE_BELOW_FLOOR', 'REGION_PRESSURE_ABOVE_CEILING'].includes(kind)) {
    return formatQuantity(lang, value, 'bar', 3);
  }
  if (['LIQUID_LIMIT_EXCEEDED', 'INJECTION_LIMIT_EXCEEDED', 'ROLE_FACT_MISMATCH', 'SET_LRAT_ON_INJECTOR', 'SET_RATE_ON_PRODUCER', 'LRAT_ABOVE_CEILING', 'NEGATIVE_SETPOINT', 'OPEN_WITHOUT_FLOW', 'SHUT_WITH_FLOW', 'WELL_OUTAGE_VIOLATED'].includes(kind)) {
    return formatQuantity(lang, value, 'm3/day', 3);
  }
  if (kind === 'PRODUCTION_FLOOR_MISSED' || kind === 'OIL_LIMIT_EXCEEDED') {
    return formatQuantity(lang, value, 't/day', 3);
  }
  if (kind === 'WATER_SUPPLY_LIMIT_EXCEEDED' || kind === 'COMPENSATION_UNDEFINED') {
    return formatQuantity(lang, value, 'm3', 3);
  }
  if (['COMPENSATION_OUT_OF_CORRIDOR', 'MATERIAL_BALANCE_BROKEN'].includes(kind)) {
    return formatQuantity(lang, value, 'fraction', 4);
  }
  return null;
};

const localizedOrRaw = (t: ReturnType<typeof useI18n>['t'], prefix: string, value: string): string => {
  const key = prefix === 'constraintStatus'
    ? `jarvis-cards.constraintStatus_${value}`
    : `jarvis-cards.${prefix}.${value}`;
  const translated = t(key);
  return translated === key ? value : translated;
};

const constraintDetailLabel = (
  constraint: string,
  status: string,
  detail: string,
  lang: 'ru' | 'en',
  t: ReturnType<typeof useI18n>['t']
): string => {
  if (status === 'not_set') return t('jarvis-cards.constraintNotCheckedDetail');
  if (status !== 'checked') return detail;

  const decimal = '(\\d+(?:\\.\\d+)?)';
  if (['injection_limits', 'liquid_limits', 'oil_limits'].includes(constraint)) {
    const annual = /the upper limit of total (?:liquid production|oil production|injection) by year is set for years (.+) and checked step by step/.exec(detail);
    if (annual !== null) return t('jarvis-cards.constraintDetail.annualLimitChecked', { years: annual[1] });
  }
  if (constraint === 'well_outages') {
    const outage = /^outage windows (\d+): the response was checked for zero rate and zero injection inside each window$/.exec(detail);
    if (outage !== null) return t('jarvis-cards.constraintDetail.outageResponseChecked', { count: formatNumber(lang, Number(outage[1]), 0) });
  }
  if (constraint === 'well_outages (static)') {
    const outage = /^outage windows (\d+): schedule events were checked for positive setpoints and OPEN inside a window$/.exec(detail);
    if (outage !== null) return t('jarvis-cards.constraintDetail.outageScheduleChecked', { count: formatNumber(lang, Number(outage[1]), 0) });
  }
  if (constraint === 'infrastructure.water_supply') {
    const water = new RegExp(`^reinjection fraction ${decimal}, lag (\\d+) steps, external inflow ${decimal} m3/day: injection checked against the water balance on (\\d+) steps$`).exec(detail);
    if (water !== null) {
      return t('jarvis-cards.constraintDetail.waterBalanceChecked', {
        fraction: formatNumber(lang, Number(water[1]), 3),
        lag: formatNumber(lang, Number(water[2]), 0),
        inflow: formatNumber(lang, Number(water[3]), 3),
        steps: formatNumber(lang, Number(water[4]), 0)
      });
    }
  }
  if (constraint === 'infrastructure.bhp_limits') {
    const pressure = new RegExp(`^bottomhole pressure corridor ${decimal}\\.\\.\\.${decimal} bar:`).exec(detail);
    if (pressure !== null) {
      return t('jarvis-cards.constraintDetail.bhpChecked', {
        low: formatNumber(lang, Number(pressure[1]), 1),
        high: formatNumber(lang, Number(pressure[2]), 1)
      });
    }
  }
  if (constraint === 'infrastructure.compensation') {
    const compensation = new RegExp(`^compensation corridor ${decimal}\\.\\.\\.${decimal}, mode ([\\w-]+): C\\(k\\) = injection / withdrawal checked over the field on (\\d+) steps under surface conditions; the formation volume factors B_o/B_w were not supplied to the validator: C\\(k\\) is computed under surface conditions, conversion to reservoir conditions was not performed$`).exec(detail);
    if (compensation !== null) {
      return t('jarvis-cards.constraintDetail.compensationChecked', {
        low: formatNumber(lang, Number(compensation[1]), 2),
        high: formatNumber(lang, Number(compensation[2]), 2),
        mode: localizedOrRaw(t, 'constraintEnforcement', compensation[3]),
        steps: formatNumber(lang, Number(compensation[4]), 0)
      });
    }
  }
  if (constraint === 'infrastructure.compensation_scope') {
    const compensation = new RegExp(`^infrastructure\\.compensation_scope = 'field_and_groups': the corridor ${decimal}\\.\\.\\.${decimal} was checked per group under surface conditions, split [\\da-f]+ of (\\d+) groups, (\\d+) step-group pairs; the formation volume factors B_o/B_w were not supplied to the validator: C\\(k\\) is computed under surface conditions, conversion to reservoir conditions was not performed$`).exec(detail);
    if (compensation !== null) {
      return t('jarvis-cards.constraintDetail.compensationGroupsChecked', {
        low: formatNumber(lang, Number(compensation[1]), 2),
        high: formatNumber(lang, Number(compensation[2]), 2),
        groups: formatNumber(lang, Number(compensation[3]), 0),
        pairs: formatNumber(lang, Number(compensation[4]), 0)
      });
    }
  }
  return detail;
};

const runReasonLabel = (reason: string, t: ReturnType<typeof useI18n>['t']): string => {
  const messages: Record<string, string> = {
    'the run check is not recorded: there is no validation/result.json file, so the number of violations is unknown': 'runReason.noValidationResult',
    'there is no constraints report: the file validation/constraints_report.json is not recorded': 'runReason.noConstraintsReport',
    'the constraints report contains no check rows, so constraint coverage is unknown': 'runReason.noConstraintRows',
    'validation/violations.json is not recorded for this run': 'runReason.noViolationFile',
    'validation/violations.json is unreadable or has an invalid format': 'runReason.invalidViolationFile'
  };
  const key = messages[reason];
  if (key !== undefined) return t(`jarvis-cards.${key}`);
  const invalidRow = /^validation\/violations\.json row (\d+) has no violation kind$/.exec(reason);
  if (invalidRow !== null) return t('jarvis-cards.runReason.rowNoKind', { row: invalidRow[1] });
  const invalidCoordinate = /^validation\/violations\.json row (\d+) has an invalid (control_step|region)$/.exec(reason);
  if (invalidCoordinate !== null) {
    const field = invalidCoordinate[2] === 'control_step' ? t('jarvis-cards.step') : t('jarvis-cards.region');
    return t('jarvis-cards.runReason.invalidCoordinate', { row: invalidCoordinate[1], field });
  }
  const invalidFields = /^validation\/violations\.json row (\d+) has invalid location or violation fields$/.exec(reason);
  if (invalidFields !== null) return t('jarvis-cards.runReason.invalidFields', { row: invalidFields[1] });
  return reason;
};

export const RunStatusCard = ({ payload, onOpen }: { payload: unknown; onOpen: (action: ConsoleAction) => void }) => {
  const { lang, t } = useI18n();
  const run = readRunStatus(payload);
  if (run === null) return <EmptyPayload />;
  const acceptance = run.acceptance;
  return (
    <div className="jarvis-run-status">
      <p className="jarvis-run-status-id">{run.run_id} · {runStatusLabel(run.status, t)}</p>
      {acceptance === null ? null : (
        <section aria-label={t('jarvis-cards.acceptance')}>
          <p className="jarvis-run-status-verdict" data-verdict={acceptance.verdict}>{translationOrRaw(`jarvis-cards.acceptance_${acceptance.verdict}`, acceptance.verdict, t)}</p>
          <p className="jarvis-run-status-summary">
            OPM: {opmStatusLabel(acceptance.opm_status, t)} · {t('jarvis-cards.submissionChecks')}: {acceptance.sound === null ? DASH : t(acceptance.sound ? 'jarvis-cards.yes' : 'jarvis-cards.no')} ·
            {' '}{t('jarvis-cards.blockingViolations')}: {acceptance.blocking_violations ?? '—'} ·
            {' '}{t('jarvis-cards.dynamicViolations')}: {acceptance.dynamic_violations ?? '—'}
          </p>
          <div className="jarvis-run-status-npv">
            <p>{t('jarvis-cards.predictedNpv')}: {acceptance.npv_sources?.predicted.value == null ? DASH : formatQuantity(lang, acceptance.npv_sources.predicted.value, 'RUB')} <small title={acceptance.npv_sources?.predicted.source}>{acceptance.npv_sources?.predicted.source?.toLowerCase().includes('surrogate prediction') ? t('jarvis-cards.npvSource.predicted') : acceptance.npv_sources?.predicted.source ?? DASH}</small></p>
            <p>{t('jarvis-cards.verifiedNpv')}: {acceptance.npv_sources?.verified.value == null ? DASH : formatQuantity(lang, acceptance.npv_sources.verified.value, 'RUB')} <small title={acceptance.npv_sources?.verified.source}>{acceptance.npv_sources?.verified.source?.toLowerCase().includes('opm verification') ? t('jarvis-cards.npvSource.verified') : acceptance.npv_sources?.verified.source ?? DASH}</small></p>
          </div>
          {acceptance.unverified_reason ? <p>{t('jarvis-cards.unverifiedChecks')}: {runReasonLabel(acceptance.unverified_reason, t)}</p> : null}
        </section>
      )}
      <section aria-label={t('jarvis-cards.constraintChecks')}>
        <h4>{t('jarvis-cards.constraintChecks')}</h4>
        {!run.constraints.recorded ? <p>{run.constraints.unavailable_reason === null ? t('jarvis-cards.constraintChecksMissing') : runReasonLabel(run.constraints.unavailable_reason, t)}</p> : (
          <ol className="jarvis-run-status-checks">
            {run.constraints.checks.map((check) => (
              <li key={check.constraint} data-status={check.status}>
                <strong>{localizedOrRaw(t, 'constraint', check.constraint)}</strong>
                <span>{localizedOrRaw(t, 'constraintStatus', check.status)} · {t('jarvis-cards.violations')}: {check.violations ?? DASH} · {t('jarvis-cards.blocking')}: {check.blocking === null ? DASH : t(check.blocking ? 'jarvis-cards.yes' : 'jarvis-cards.no')}</span>
                {check.enforcement ? <span>{t('jarvis-cards.enforcement')}: {localizedOrRaw(t, 'constraintEnforcement', check.enforcement)}</span> : null}
                {check.detail ? <small title={check.detail}>{constraintDetailLabel(check.constraint, check.status, check.detail, lang, t)}</small> : null}
              </li>
            ))}
          </ol>
        )}
      </section>
      <section>
        <h4>{t('jarvis-cards.violationLocations')}</h4>
        {!run.violation_locations.recorded ? <p>{run.violation_locations.reason === null ? t('jarvis-cards.violationLocationsMissing') : runReasonLabel(run.violation_locations.reason, t)}</p> : (
          <>
            <p>{t('jarvis-cards.violationLocationsCount', { count: run.violation_locations.total ?? run.violation_locations.rows.length })}</p>
            <ol className="jarvis-run-status-list">
              {run.violation_locations.rows.map((row, index) => {
                const formattedValue = violationValue(lang, row.kind, row.value);
                return (
                  <li key={`${row.kind}-${row.control_step}-${row.well}-${index}`}>
                    <span><strong title={row.kind}>{violationKindLabel(row.kind, t)}</strong>{row.blocking ? ` · ${t('jarvis-cards.blocking')}` : ''}</span>
                    <span>{violationDetailLabel(row.kind, row.detail, lang, t)}{formattedValue === null ? '' : ` · ${formattedValue}`}</span>
                    <span>{row.well === null ? (row.region === null ? t('jarvis-cards.fieldLevel') : `${t('jarvis-cards.region')} ${row.region}`) : `${t('jarvis-cards.well')} ${row.well}`}{row.control_step === null ? '' : ` · ${t('jarvis-cards.step')} ${row.control_step}`}</span>
                    {row.well === null && row.control_step === null ? null : (
                      <button type="button" onClick={() => onOpen({
                        workspace: 'field', view: 'projection', run_id: run.run_id,
                        ...(row.well === null ? {} : { well: row.well }),
                        ...(row.control_step === null ? {} : { step: row.control_step })
                      })}>{t('jarvis-cards.openViolationLocation')}</button>
                    )}
                  </li>
                );
              })}
            </ol>
            {run.violation_locations.truncated ? <p>{t('jarvis-cards.violationLocationsTruncated')}</p> : null}
          </>
        )}
      </section>
    </div>
  );
};
