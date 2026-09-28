import { DASH, formatNumber, formatPercent, formatQuantity } from '@/shared/lib/format';
import type { useI18n } from '@/shared/i18n/I18nContext';
import type { Lang } from '@/shared/i18n/dictionaries';

type Translate = ReturnType<typeof useI18n>['t'];

export const displayInputKey = (key: string, t: Translate): string => {
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

export const displayValue = (
  value: unknown,
  lang: Lang,
  key = '',
  t?: Translate
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

export const displayRateValue = (value: unknown, lang: Lang): string =>
  typeof value === 'number'
    ? formatQuantity(lang, value, 'm3/day', 3)
    : displayValue(value, lang);
