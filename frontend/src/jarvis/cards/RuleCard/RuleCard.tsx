import { useRef } from 'react';
import { DASH, formatCalendarDate, formatNumber, formatPercent, formatQuantity } from '@/shared/lib/format';
import { useI18n } from '@/shared/i18n/I18nContext';
import type { Lang } from '@/shared/i18n/dictionaries';
import { readRule, readRuleSummary } from '@/jarvis/cards/payloads';
import { EmptyPayload } from '@/jarvis/cards/EmptyPayload/EmptyPayload';
import type { RulePayload } from '@/jarvis/cards/payloads/payloadTypes';
import { isRecord, isStr } from '@/jarvis/cards/payloads/payloadPrimitives';
import { readRunSeries } from '@/jarvis/cards/payloads/runSeriesPayload';
import { RunSeriesPlot } from '@/jarvis/cards/RuleCard/RunSeriesPlot';
import { translationOrRaw } from '@/jarvis/cards/lib/translationFallback';
import { councilCodeLabel } from '@/jarvis/cards/lib/councilCodeLabel';
import { opmStatusLabel } from '@/jarvis/cards/lib/opmStatusLabel';
import type { ConsoleAction } from '@/jarvis/actions/lib/consoleAction';
import './RuleCard.css';

const RuleBody = ({ rule }: { rule: RulePayload }) => {
  const { lang, t } = useI18n();
  const inputs = Object.entries(rule.inputs);
  const decisionLabel = (value: string) => translationOrRaw(`jarvis-cards.councilaction.${value}`, value, t);
  const ruleName = translationOrRaw(`jarvis-cards.ruleFactName.${rule.rule}`, rule.name, t);
  const ruleStatement = translationOrRaw(`jarvis-cards.ruleStatement.${rule.rule}`, rule.statement, t);

  return (
    <div className="jarvis-rule">
      <p className="jarvis-rule-name">{ruleName}</p>
      <p className="jarvis-rule-statement">{ruleStatement}</p>
      {inputs.length === 0 ? null : (
        <dl className="jarvis-rule-inputs">
          <dt className="jarvis-rule-inputs-label">{t('jarvis-cards.ruleInputs')}</dt>
          {inputs.map(([key, value]) => (
            <dd className="jarvis-rule-input" key={key}>
              <span className="jarvis-rule-input-key">{displayInputKey(key, t)}</span>
              <span className="jarvis-rule-input-value">{displayValue(value, lang, key, t)}</span>
            </dd>
          ))}
        </dl>
      )}
      <p className="jarvis-rule-decision">
        <span className="jarvis-rule-decision-label">{t('jarvis-cards.ruleDecision')}</span>
        <code className="jarvis-rule-decision-value" title={rule.decision || undefined}>{rule.decision ? decisionLabel(rule.decision) : DASH}</code>
      </p>
      <p className="jarvis-rule-impact">
        <span className="jarvis-rule-impact-label">{t('jarvis-cards.ruleImpact')}</span>
        {rule.delta_npv === null ? (
          <span className="jarvis-rule-unmeasured">{t('jarvis-cards.ruleUnmeasured')}</span>
        ) : (
          <span className="jarvis-rule-impact-value">
            {formatQuantity(lang, rule.delta_npv, 'RUB')}
            {rule.share === null ? null : ` · ${formatPercent(lang, rule.share)}`}
          </span>
        )}
      </p>
    </div>
  );
};

const displayInputKey = (key: string, t: ReturnType<typeof useI18n>['t']): string => {
  const labelKey = `jarvis-cards.ruleInput.${key}`;
  const translated = t(labelKey);
  if (translated !== labelKey) return translated;
  return key
    .replace(/_m3_per_day$/i, ' (m³/day)')
    .replace(/_rub_per_m3$/i, ' (RUB/m³)')
    .replace(/_rub_per_t$/i, ' (RUB/t)')
    .replace(/_t_per_m3$/i, ' (t/m³)')
    .replace(/_rub$/i, ' (RUB)')
    .replace(/_m3$/i, ' (m³)')
    .replaceAll('_', ' ');
};

const displayValue = (
  value: unknown,
  lang: Lang,
  key = '',
  t?: ReturnType<typeof useI18n>['t']
): string => {
  if (typeof value === 'number') {
    const normalized = key.toLowerCase();
    if (normalized.includes('watercut') || normalized.includes('share')) return formatPercent(lang, value);
    if (normalized.includes('bhp') || normalized.includes('pressure')) return formatQuantity(lang, value, 'bar', 3);
    if (normalized.includes('rub_per_m3')) return formatQuantity(lang, value, 'RUB/m3', 3);
    if (normalized.includes('rub_per_t')) return formatQuantity(lang, value, 'RUB/t', 3);
    if (normalized.includes('t_per_m3')) return formatQuantity(lang, value, 't/m3', 4);
    if (normalized === 'theta_r2_gain') return formatQuantity(lang, value, 'coefficient', 3);
    if (normalized.includes('npv') || normalized.includes('rub')) return formatQuantity(lang, value, 'RUB', 0);
    if (normalized.endsWith('_enforced')) return t ? t(value === 0 ? 'jarvis-cards.no' : 'jarvis-cards.yes') : String(value !== 0);
    if (normalized === 'corridor_low' || normalized === 'corridor_high' || normalized.includes('target_compensation') || normalized === 'theta_r3_reopen_margin') {
      return formatQuantity(lang, value, 'fraction', 3);
    }
    if (normalized.includes('compensation') || normalized.includes('residual') || normalized.includes('fraction')) {
      return formatQuantity(lang, value, 'fraction', 3);
    }
    if (normalized.includes('rate') || normalized.includes('setpoint') || normalized === 'set_lrat' || normalized === 'set_rate' || normalized.endsWith('_m3_per_day')) {
      return formatQuantity(lang, value, 'm3/day', 3);
    }
    if (normalized.includes('_m3') || normalized.includes('volume')) return formatQuantity(lang, value, 'm3', 3);
    if (normalized.includes('step') || normalized.endsWith('_count') || normalized === 'producers_covered') {
      return formatQuantity(lang, value, normalized.includes('step') ? 'steps' : 'wells', 0);
    }
    if (normalized.includes('months')) return formatQuantity(lang, value, 'months', 1);
    if (normalized.endsWith('_years')) return formatQuantity(lang, value, 'years', 1);
    if (normalized.endsWith('_scale')) return formatQuantity(lang, value, 'fraction', 3);
    const number = formatNumber(lang, value, 3);
    return key && t ? `${number} ${t('jarvis-cards.unitNotSpecified')}` : number;
  }
  if (typeof value === 'boolean') return t ? t(value ? 'jarvis-cards.yes' : 'jarvis-cards.no') : String(value);
  if (typeof value === 'string') return value;
  return DASH;
};

const displayRateValue = (value: unknown, lang: Lang): string =>
  typeof value === 'number'
    ? formatQuantity(lang, value, 'm3/day', 3)
    : displayValue(value, lang);

const EvidenceBody = ({
  payload,
  action,
  onOpen
}: {
  payload: Record<string, unknown>;
  action?: ConsoleAction;
  onOpen: (action: ConsoleAction) => void;
}) => {
  const { lang, t } = useI18n();
  const evidenceDetails = useRef<HTMLDetailsElement>(null);
  const runChart = useRef<HTMLElement>(null);
  const observation = isRecord(payload.input_observation) ? payload.input_observation : null;
  const check = isRecord(payload.plan_check) ? payload.plan_check : null;
  const evaluations = isRecord(payload.evaluation_sources) ? payload.evaluation_sources : null;
  const prediction = evaluations && isRecord(evaluations.surrogate_prediction) ? evaluations.surrogate_prediction : null;
  const economics = evaluations && isRecord(evaluations.economic_evaluation) ? evaluations.economic_evaluation : null;
  const measuredNpv = economics?.measured_npv_rub ?? economics?.measured_npv;
  const feedbackComparison = isRecord(payload.feedback_comparison) ? payload.feedback_comparison : null;
  const feedbackMetrics = feedbackComparison && isRecord(feedbackComparison.metrics) ? feedbackComparison.metrics : null;
  const alternativeComparison = isRecord(payload.alternative_comparison) ? payload.alternative_comparison : null;
  const summary = isRecord(payload.decision_summary) ? payload.decision_summary : null;
  const runSeries = readRunSeries(payload.run_series);
  const shortHash = (value: unknown) => typeof value === 'string' ? value.slice(0, 12) : DASH;
  const eventKindLabel = (value: unknown) => typeof value === 'string'
    ? translationOrRaw(`jarvis-cards.councilaction.${value}`, value, t)
    : DASH;
  const decisionEvidenceLabel = (value: unknown): string => {
    if (!isStr(value)) return displayValue(value, lang, '', t);
    const match = /^([A-Z][A-Z0-9_]*)(?:\s+(-?\d+(?:\.\d+)?))?$/.exec(value.trim());
    if (match === null) return value;
    const label = councilCodeLabel('action', match[1], t);
    if (label === match[1]) return value;
    const rate = match[2] === undefined ? '' : ` ${displayValue(Number(match[2]), lang, match[1], t)}`;
    return `${label}${rate}`;
  };
  const facts = Array.isArray(payload.rule_facts) ? payload.rule_facts.filter(isRecord) : [];
  const factHeader = (fact: Record<string, unknown>, rule: unknown) => [
    isStr(fact.level) ? translationOrRaw(`jarvis-cards.ruleFactLevel.${fact.level}`, fact.level, t) : null,
    isStr(fact.agent) ? councilCodeLabel('agent', fact.agent, t) : null,
    isStr(rule) ? translationOrRaw(`jarvis-cards.ruleFactName.${rule}`, rule, t) : null
  ].filter(isStr).join(' · ');
  const eventList = (value: unknown) => Array.isArray(value) ? value.filter(isRecord) : [];
  const renderEvents = (events: Record<string, unknown>[]) => events.length === 0 ? (
    <span>{DASH}</span>
  ) : (
    <ul className="jarvis-rule-evidence-list">
      {events.map((event, index) => (
        <li key={`${String(event.well ?? '')}-${String(event.kind ?? '')}-${index}`}>
          <code>{[event.kind && eventKindLabel(event.kind), event.well && `${t('jarvis-cards.well')} ${event.well}`, event.value != null && displayValue(event.value, lang, isStr(event.kind) ? event.kind : '', t)].filter(Boolean).join(' · ')}</code>
        </li>
      ))}
    </ul>
  );
  const eventSummary = (value: unknown) => {
    const events = eventList(value);
    if (events.length === 0) return DASH;
    return events.map((event) => [event.kind && eventKindLabel(event.kind), event.well && `${t('jarvis-cards.well')} ${event.well}`, event.value != null && displayValue(event.value, lang, isStr(event.kind) ? event.kind : '', t)].filter(Boolean).join(' ')).join('; ');
  };

  return (
    <div className="jarvis-rule">
      <p className="jarvis-rule-name">
        {isStr(payload.run_id) ? `${t('jarvis-cards.evidenceRun')}: ${payload.run_id}` : t('jarvis-cards.recordedEvidence')}
      </p>
      <p className="jarvis-rule-statement">
        {`${t('jarvis-cards.well')}: ${displayValue(payload.well, lang)} · ${t('jarvis-cards.step')}: ${displayValue(payload.step, lang)}`}
      </p>
      <div className="jarvis-rule-primary-actions">
        {runSeries ? (
          <button
            type="button"
            onClick={() => {
              const chart = runChart.current;
              if (chart === null) return;
              chart.scrollIntoView?.({ behavior: 'smooth', block: 'nearest' });
              chart.focus();
            }}
          >
            {t('jarvis-cards.openRunChart')}
          </button>
        ) : null}
        <button
          type="button"
          onClick={() => {
            const details = evidenceDetails.current;
            if (details === null) return;
            details.open = true;
            details.scrollIntoView?.({ behavior: 'smooth', block: 'nearest' });
            details.querySelector('summary')?.focus();
          }}
        >
          {t('jarvis-cards.openJournal')}
        </button>
      </div>
      {summary ? (
        <section className="jarvis-rule-evidence-section">
          <strong>{t('jarvis-cards.decisionSummary')}</strong>
          <p>{`${t('jarvis-cards.observedSetpoint')}: ${displayValue(summary.observed_setpoint_m3_per_day, lang)} m³/сут`}</p>
          <p>{`${t('jarvis-cards.recordedProposal')}: ${eventSummary(summary.proposal_events)}`}</p>
          <p>{`${t('jarvis-cards.finalCommand')}: ${eventSummary(summary.final_events)}`}</p>
          <small>{t('jarvis-cards.summaryEvidenceOnly')}</small>
        </section>
      ) : null}
      {runSeries ? (
        <section ref={runChart} tabIndex={-1} className="jarvis-rule-evidence-section">
          <strong>{t('jarvis-cards.runSeriesTitle', { run: runSeries.run_id })}</strong>
          <RunSeriesPlot series={runSeries} step={typeof payload.step === 'number' ? payload.step : undefined} />
          {action?.scenario && action.connections_available && isStr(payload.well) ? (
            <div className="jarvis-rule-map-action">
              <p>{t('jarvis-cards.showcaseLinksNotice', {
                scenario: isRecord(payload.connectivity_source) && isStr(payload.connectivity_source.scenario)
                  ? payload.connectivity_source.scenario
                  : action.scenario
              })}</p>
              <button
                type="button"
                onClick={() => onOpen({
                  scenario: isRecord(payload.connectivity_source) && isStr(payload.connectivity_source.scenario)
                    ? payload.connectivity_source.scenario
                    : action.scenario,
                  run_id: runSeries.run_id,
                  workspace: 'field',
                  view: 'projection',
                  well: payload.well as string,
                  ...(typeof payload.step === 'number' ? { step: payload.step } : {})
                })}
              >
                {t('jarvis-cards.showConnections')}
              </button>
            </div>
          ) : null}
        </section>
      ) : null}
      {facts.length > 0 ? (
        <section className="jarvis-rule-evidence-section">
          <strong>{t('jarvis-cards.keyFactors')}</strong>
          {facts.slice(0, 4).map((fact, index) => {
            const entry = isRecord(fact.entry) ? fact.entry : {};
            return (
              <p className="jarvis-rule-impact" key={`${String(fact.level ?? '')}-${index}`}>
                <strong>{factHeader(fact, entry.rule)}</strong>
                {`: ${decisionEvidenceLabel(entry.decision)}`}
              </p>
            );
          })}
        </section>
      ) : null}
      {check ? (
        <section className="jarvis-rule-evidence-section">
          <strong>{t('jarvis-cards.planCheck')}</strong>
          <p>{`OPM: ${opmStatusLabel(isStr(check.opm_status) ? check.opm_status : null, t)} · ${t('jarvis-cards.constraintsPassed')}: ${displayValue(check.sound, lang, '', t)}`}</p>
          <p>{`${t('jarvis-cards.blockingViolations')}: ${displayValue(check.blocking_dynamic_violations, lang)}`}</p>
        </section>
      ) : null}
      {feedbackComparison?.status === 'pointwise-state-comparison' && feedbackMetrics ? (
        <section className="jarvis-rule-evidence-section">
          <strong>{t('jarvis-cards.feedbackComparisonTitle')}</strong>
          <p>{`${t('jarvis-cards.feedbackComparisonSource')}: ${displayValue(feedbackComparison.feedback_source_run_id, lang)} · ${isStr(feedbackComparison.date) ? formatCalendarDate(lang, feedbackComparison.date) : DASH}`}</p>
          {Object.entries(feedbackMetrics).map(([key, value]) => {
            if (!isRecord(value)) return null;
            const label = key === 'oil_rate_m3_per_day'
              ? t('jarvis-cards.oilRate')
              : key === 'injection_rate_m3_per_day'
                ? t('jarvis-cards.injectionRate')
                : key;
            return (
              <p key={key}>{`${label}: ${displayRateValue(value.feedback, lang)} → ${displayRateValue(value.evaluation, lang)} (${t('jarvis-cards.delta')}: ${displayRateValue(value.delta_evaluation_minus_feedback, lang)})`}</p>
            );
          })}
          <small>{t('jarvis-cards.feedbackComparisonCaveat')}</small>
        </section>
      ) : null}
      <details ref={evidenceDetails} className="jarvis-rule-evidence-details">
        <summary>{t('jarvis-cards.decisionEvidenceDetails')}</summary>
      {observation ? (
        <section className="jarvis-rule-evidence-section">
          <strong>{t('jarvis-cards.inputObservation')}</strong>
          <dl className="jarvis-rule-inputs">
            {Object.entries(observation).map(([key, value]) => (
              <dd className="jarvis-rule-input" key={key}>
                <span className="jarvis-rule-input-key">{displayInputKey(key, t)}</span>
                <span className="jarvis-rule-input-value">{displayValue(value, lang, key, t)}</span>
              </dd>
            ))}
          </dl>
        </section>
      ) : null}
      {facts.map((fact, index) => {
        const entry = isRecord(fact.entry) ? fact.entry : {};
        const inputs = isRecord(entry.inputs) ? entry.inputs : {};
        return (
          <section className="jarvis-rule-evidence-section" key={`${String(fact.level ?? '')}-${String(entry.rule ?? '')}-${index}`}>
            <strong>{factHeader(fact, entry.rule)}</strong>
            <p className="jarvis-rule-decision"><code>{decisionEvidenceLabel(entry.decision)}</code></p>
            <dl className="jarvis-rule-inputs">
              {Object.entries(inputs).map(([key, value]) => (
                <dd className="jarvis-rule-input" key={key}>
                  <span className="jarvis-rule-input-key">{displayInputKey(key, t)}</span>
                  <span className="jarvis-rule-input-value">{displayValue(value, lang, key, t)}</span>
                </dd>
              ))}
            </dl>
          </section>
        );
      })}
      {facts.length === 0 ? <p className="jarvis-rule-impact">{t('jarvis-cards.noRulesFiredRecorded')}</p> : null}
      <section className="jarvis-rule-evidence-section">
        <strong>{t('jarvis-cards.hierarchyProposed')}</strong>
        {payload.hierarchy_action_status === 'no-proposal-recorded' ? <span>{t('jarvis-cards.noProposalRecorded')}</span> : null}
        {renderEvents(eventList(payload.hierarchy_proposed_events))}
      </section>
      <section className="jarvis-rule-evidence-section">
        <strong>{t('jarvis-cards.finalSchedule')}</strong>
        {payload.final_action_status === 'no-final-event-recorded' ? <span>{t('jarvis-cards.noFinalEventRecorded')}</span> : null}
        {renderEvents(eventList(payload.final_schedule_events))}
      </section>
      {evaluations ? (
        <section className="jarvis-rule-evidence-section">
          <strong>{t('jarvis-cards.sourceResults')}</strong>
          <p>{`${t('jarvis-cards.feedbackRun')}: ${displayValue(evaluations.feedback_source_run_id, lang)}`}</p>
          <p>{`${t('jarvis-cards.feedbackResponse')}: ${shortHash(evaluations.feedback_response_hash)}`}</p>
          <p>{`${t('jarvis-cards.evaluationResponse')}: ${shortHash(economics?.source_response_hash)}`}</p>
          {typeof evaluations.feedback_response_matches_evaluation === 'boolean' ? (
            <p>{`${t('jarvis-cards.feedbackMatchesEvaluation')}: ${t(evaluations.feedback_response_matches_evaluation ? 'jarvis-cards.sourceHashesMatch' : 'jarvis-cards.sourceHashesDiffer')}`}</p>
          ) : null}
          <p>{`${t('jarvis-cards.surrogateEstimate')}: ${typeof prediction?.npv === 'number' ? formatQuantity(lang, prediction.npv, 'RUB') : displayValue(prediction?.npv, lang)}`}</p>
          <p>{`${t('jarvis-cards.economicEvaluation')}: ${typeof measuredNpv === 'number' ? formatQuantity(lang, measuredNpv, 'RUB') : displayValue(measuredNpv, lang)}`}</p>
          <p>{`${t('jarvis-cards.economicSourceRun')}: ${displayValue(economics?.source_run_id, lang)}`}</p>
        </section>
      ) : null}
      {isStr(payload.alternative_status) ? (
        <p className="jarvis-rule-impact">
          {t(payload.alternative_status === 'recorded-comparison'
            ? 'jarvis-cards.alternativeRecordedComparison'
            : payload.alternative_status === 'state-comparison-only'
              ? 'jarvis-cards.alternativeStateOnly'
              : 'jarvis-cards.alternativeNeedsCalculation')}
        </p>
      ) : null}
      {payload.alternative_status === 'recorded-comparison' && alternativeComparison ? (
        <section className="jarvis-rule-evidence-section">
          <strong>{t('jarvis-cards.recordedAlternativeComparison')}</strong>
          {Object.entries(alternativeComparison).filter(([key]) => key !== 'recorded').map(([key, value]) => (
            <p key={key}>{displayInputKey(key, t)}: {displayValue(value, lang, key, t)}</p>
          ))}
        </section>
      ) : null}
      {payload.projection_status === 'not-recorded-separately' ? (
        <p className="jarvis-rule-impact">{t('jarvis-cards.projectionNotRecorded')}</p>
      ) : null}
      {isStr(payload.date) ? <p className="jarvis-rule-impact">{formatCalendarDate(lang, payload.date)}</p> : null}
      {payload.date_status === 'control-date-axis-unavailable' ? (
        <p className="jarvis-rule-impact">{t('jarvis-cards.controlDateUnavailable')}</p>
      ) : null}
      </details>
    </div>
  );
};

export const RuleCard = ({
  payload,
  action,
  onOpen
}: {
  payload: unknown;
  action?: ConsoleAction;
  onOpen: (action: ConsoleAction) => void;
}) => {
  if (isRecord(payload) && Array.isArray(payload.rule_facts)) {
    return <EvidenceBody payload={payload} action={action} onOpen={onOpen} />;
  }
  const single = readRule(payload);
  if (single !== null) {
    return <RuleBody rule={single} />;
  }
  const summary = readRuleSummary(payload);
  if (summary === null) {
    return <EmptyPayload />;
  }
  return (
    <div className="jarvis-rule-list">
      {summary.rules.map((rule) => (
        <RuleBody key={rule.rule} rule={rule} />
      ))}
    </div>
  );
};
