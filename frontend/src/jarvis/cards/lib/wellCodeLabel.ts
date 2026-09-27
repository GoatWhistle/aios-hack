import type { Translate } from '@/shared/i18n/I18nContext';

export type WellCodeCategory = 'availability' | 'role' | 'status';

export const wellCodeLabel = (value: string | null, category: WellCodeCategory, t: Translate): string => {
  if (value === null || value.length === 0) return '—';
  const key = `steps.${category}.${value}`;
  const translated = t(key);
  return translated === key ? value : translated;
};
