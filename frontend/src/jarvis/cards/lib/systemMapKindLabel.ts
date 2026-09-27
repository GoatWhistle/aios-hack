import type { Translate } from '@/shared/i18n/I18nContext';

export const systemMapKindLabel = (kind: string, t: Translate): string => {
  const key = `jarvis-cards.systemMapKind.${kind}`;
  const translated = t(key);
  return translated === key ? kind : translated;
};
