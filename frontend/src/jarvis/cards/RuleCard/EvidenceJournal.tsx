import type { ReactNode, RefObject } from 'react';
import { DASH, formatCalendarDate, formatQuantity } from '@/shared/lib/format';
import { useI18n } from '@/shared/i18n/I18nContext';
import { isRecord, isStr } from '@/jarvis/cards/payloads/payloadPrimitives';
import { displayInputKey, displayValue } from '@/jarvis/cards/RuleCard/ruleValues';

interface EvidenceJournalProps {
  payload: Record<string, unknown>;
  facts: Record<string, unknown>[];
  detailsRef: RefObject<HTMLDetailsElement | null>;
  factHeader: (fact: Record<string, unknown>, rule: unknown) => string;
  decisionEvidenceLabel: (value: unknown) => string;
  renderEvents: (events: Record<string, unknown>[]) => ReactNode;
  eventList: (value: unknown) => Record<string, unknown>[];
}

const InputList = ({ entries }: { entries: [string, unknown][] }) => {
  const { lang, t } = useI18n();
  return (
    <dl className="jarvis-rule-inputs">
      {entries.map(([key, value]) => (
        <dd className="jarvis-rule-input" key={key}>
          <span className="jarvis-rule-input-key">{displayInputKey(key, t)}</span>
          <span className="jarvis-rule-input-value">{displayValue(value, lang, key, t)}</span>
        </dd>
      ))}
    </dl>
  );
};

export const EvidenceJournal = ({
  payload,
  facts,
  detailsRef,
  factHeader,
  decisionEvidenceLabel,
  renderEvents,
  eventList
}: EvidenceJournalProps) => {
  const { lang, t } = useI18n();
  const observation = isRecord(payload.input_observation) ? payload.input_observation : null;
  const evaluations = isRecord(payload.evaluation_sources) ? payload.evaluation_sources : null;
  const prediction = evaluations && isRecord(evaluations.surrogate_prediction) ? evaluations.surrogate_prediction : null;
  const economics = evaluations && isRecord(evaluations.economic_evaluation) ? evaluations.economic_evaluation : null;
  const measuredNpv = economics?.measured_npv_rub ?? economics?.measured_npv;
  const alternativeComparison = isRecord(payload.alternative_comparison) ? payload.alternative_comparison : null;
  const shortHash = (value: unknown) => typeof value === 'string' ? value.slice(0, 12) : DASH;

  return (
    <details ref={detailsRef} className="jarvis-rule-evidence-details">
      <summary>{t('jarvis-cards.decisionEvidenceDetails')}</summary>
      {observation ? (
        <section className="jarvis-rule-evidence-section">
          <strong>{t('jarvis-cards.inputObservation')}</strong>
          <InputList entries={Object.entries(observation)} />
        </section>
      ) : null}
      {facts.map((fact, index) => {
        const entry = isRecord(fact.entry) ? fact.entry : {};
        const inputs = isRecord(entry.inputs) ? entry.inputs : {};
        return (
          <section className="jarvis-rule-evidence-section" key={`${String(fact.level ?? '')}-${String(entry.rule ?? '')}-${index}`}>
            <strong>{factHeader(fact, entry.rule)}</strong>
            <p className="jarvis-rule-decision"><code>{decisionEvidenceLabel(entry.decision)}</code></p>
            <InputList entries={Object.entries(inputs)} />
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
  );
};
