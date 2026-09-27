import { formatCalendarDate, formatNumber, formatPercent, formatQuantity } from '@/shared/lib/format';
import { useI18n } from '@/shared/i18n/I18nContext';
import { readPattern } from '@/jarvis/cards/payloads';
import { diagnosticPatternLabel } from '@/jarvis/cards/lib/diagnosticPatternLabel';
import { EmptyPayload } from '@/jarvis/cards/EmptyPayload/EmptyPayload';
import './PatternCard.css';

export const PatternCard = ({ payload }: { payload: unknown }) => {
  const { lang, t } = useI18n();
  const pattern = readPattern(payload);
  if (pattern === null) {
    return <EmptyPayload />;
  }
  const inputs = Object.entries(pattern.inputs);
  const severityKey = `jarvis-cards.patternSeverity.${pattern.severity}`;
  const localizedSeverity = t(severityKey);
  const inputLabel = (key: string): string => {
    const labelKey = `jarvis-cards.patternInput.${key}`;
    const label = t(labelKey);
    return label === labelKey ? key : label;
  };
  const formatInput = (key: string, value: number): string => {
    if (key === 'watercut_prev' || key === 'watercut_curr') return formatPercent(lang, value);
    if (key === 'bhp_prev' || key === 'bhp_curr') return formatQuantity(lang, value, 'bar', 3);
    if (key === 'liquid_rate' || key === 'liquid_delta' || key === 'production_delta') {
      return formatQuantity(lang, value, 'm3/day', 3);
    }
    if (key === 'oil_delta') return formatQuantity(lang, value, 'kg', 3);
    if (key === 'injection_delta') return formatQuantity(lang, value, 'm3', 3);
    if (key === 'lag_steps') return formatQuantity(lang, value, 'steps', 0);
    if (key === 'injection_total') {
      return `${formatNumber(lang, value, 3)} ${t('jarvis-cards.patternUnit.rateSamples')}`;
    }
    return `${formatNumber(lang, value, 3)} ${t('jarvis-cards.unitNotSpecified')}`;
  };

  return (
    <div className="jarvis-pattern">
      <p className="jarvis-pattern-name" title={pattern.pattern_id}>{diagnosticPatternLabel(pattern.pattern_id, pattern.name, t)}</p>
      <p className="jarvis-pattern-meta">
        <span className="jarvis-pattern-well">{pattern.well}</span>
        <span className="jarvis-pattern-severity" data-severity={pattern.severity}>
          {t('jarvis-cards.patternSeverity')}: {localizedSeverity === severityKey ? pattern.severity : localizedSeverity}
        </span>
      </p>
      {pattern.window === null ? null : (
        <p className="jarvis-pattern-window">
          {t('jarvis-cards.patternWindow')} {pattern.window.from_step}–{pattern.window.to_step}
          {pattern.window_dates === null ? '' : ` · ${formatCalendarDate(lang, pattern.window_dates[0])} – ${formatCalendarDate(lang, pattern.window_dates[1])}`}
        </p>
      )}
      {pattern.date === null ? null : (
        <p className="jarvis-pattern-date">
          {formatCalendarDate(lang, pattern.date)}{pattern.step === null ? '' : ` · ${t('jarvis-cards.step')} ${pattern.step}`}
        </p>
      )}
      {inputs.length === 0 ? null : (
        <dl className="jarvis-pattern-inputs">
          {inputs.map(([key, value]) => (
            <div key={key}>
              <dt>{inputLabel(key)}</dt>
              <dd>{formatInput(key, value)}</dd>
            </div>
          ))}
        </dl>
      )}
    </div>
  );
};
