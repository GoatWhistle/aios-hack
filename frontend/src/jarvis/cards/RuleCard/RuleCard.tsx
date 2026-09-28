import { DASH, formatPercent, formatQuantity } from '@/shared/lib/format';
import { useI18n } from '@/shared/i18n/I18nContext';
import { readRule, readRuleSummary } from '@/jarvis/cards/payloads';
import { EmptyPayload } from '@/jarvis/cards/EmptyPayload/EmptyPayload';
import type { RulePayload } from '@/jarvis/cards/payloads/payloadTypes';
import { isRecord } from '@/jarvis/cards/payloads/payloadPrimitives';
import { translationOrRaw } from '@/jarvis/cards/lib/translationFallback';
import { displayInputKey, displayValue } from '@/jarvis/cards/RuleCard/ruleValues';
import { EvidenceBody } from '@/jarvis/cards/RuleCard/EvidenceBody';
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

interface RuleCardProps {
  payload: unknown;
  action?: ConsoleAction;
  onOpen: (action: ConsoleAction) => void;
}

export const RuleCard = ({ payload, action, onOpen }: RuleCardProps) => {
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
