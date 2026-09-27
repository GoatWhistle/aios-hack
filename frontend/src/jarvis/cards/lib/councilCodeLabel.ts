import type { Translate } from '@/shared/i18n/I18nContext';

export const councilCodeLabel = (
  category: 'level' | 'verdict' | 'agent' | 'action',
  value: string | null,
  t: Translate
): string => {
  if (value === null || value.length === 0) return '—';
  const key = `jarvis-cards.council${category}.${value}`;
  const translated = t(key);
  return translated === key ? value : translated;
};
