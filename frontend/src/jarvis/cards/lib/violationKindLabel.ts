import type { Translate } from '@/shared/i18n/I18nContext';

export const violationKindLabel = (kind: string, t: Translate): string => {
  const key = `jarvis-cards.violationKind.${kind}`;
  const translated = t(key);
  return translated === key ? kind : translated;
};
