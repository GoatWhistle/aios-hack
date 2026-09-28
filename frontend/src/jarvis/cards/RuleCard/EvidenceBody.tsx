import { useRef } from 'react';
import { DASH, formatCalendarDate } from '@/shared/lib/format';
import { useI18n } from '@/shared/i18n/I18nContext';
import { isRecord, isStr } from '@/jarvis/cards/payloads/payloadPrimitives';
import { readRunSeries } from '@/jarvis/cards/payloads/runSeriesPayload';
import { RunSeriesPlot } from '@/jarvis/cards/RuleCard/RunSeriesPlot';
import { translationOrRaw } from '@/jarvis/cards/lib/translationFallback';
import { councilCodeLabel } from '@/jarvis/cards/lib/councilCodeLabel';
import { opmStatusLabel } from '@/jarvis/cards/lib/opmStatusLabel';
import { displayRateValue, displayValue } from '@/jarvis/cards/RuleCard/ruleValues';
import { EvidenceJournal } from '@/jarvis/cards/RuleCard/EvidenceJournal';
import type { ConsoleAction } from '@/jarvis/actions/lib/consoleAction';

interface EvidenceBodyProps {
  payload: Record<string, unknown>;
  action?: ConsoleAction;
  onOpen: (action: ConsoleAction) => void;
}

export const EvidenceBody = ({ payload, action, onOpen }: EvidenceBodyProps) => {
  const { lang, t } = useI18n();
  const evidenceDetails = useRef<HTMLDetailsElement>(null);
  const runChart = useRef<HTMLElement>(null);
  const check = isRecord(payload.plan_check) ? payload.plan_check : null;
  const feedbackComparison = isRecord(payload.feedback_comparison) ? payload.feedback_comparison : null;
  const feedbackMetrics = feedbackComparison && isRecord(feedbackComparison.metrics) ? feedbackComparison.metrics : null;
  const summary = isRecord(payload.decision_summary) ? payload.decision_summary : null;
  const runSeries = readRunSeries(payload.run_series);
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
          <p>{`${t('jarvis-cards.observedSetpoint')}: ${displayValue(summary.observed_setpoint_m3_per_day, lang, 'setpoint_m3_per_day', t)}`}</p>
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
      <EvidenceJournal
        payload={payload}
        facts={facts}
        detailsRef={evidenceDetails}
        factHeader={factHeader}
        decisionEvidenceLabel={decisionEvidenceLabel}
        renderEvents={renderEvents}
        eventList={eventList}
      />
    </div>
  );
};
