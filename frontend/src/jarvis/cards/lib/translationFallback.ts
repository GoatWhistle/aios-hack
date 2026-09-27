import type { Translate } from '@/shared/i18n/I18nContext';

export const translationOrRaw = (key: string, raw: string, t: Translate): string => {
  const translated = t(key);
  return translated === key ? raw : translated;
};
