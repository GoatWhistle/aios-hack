import type { Translate } from '@/shared/i18n/I18nContext';

export const diagnosticPatternLabel = (
  patternId: string | null,
  recordedName: string | null,
  t: Translate
): string => {
  if (patternId === null) return recordedName ?? '—';
  const key = `jarvis-cards.pattern.${patternId}`;
  const translated = t(key);
  return translated === key ? recordedName ?? patternId : translated;
};
