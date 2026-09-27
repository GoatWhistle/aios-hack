import type { Translate } from '@/shared/i18n/I18nContext';
import { DASH } from '@/shared/lib/format';

const OPM_STATUS_KEYS: Readonly<Record<string, string>> = {
  OK: 'jarvis-cards.opmStatus_ok',
  NOT_CONVERGED: 'jarvis-cards.opmStatus_not_converged',
  FAILED: 'jarvis-cards.opmStatus_failed'
};

export const opmStatusLabel = (status: string | null, t: Translate): string => {
  if (status === null) return DASH;
  const key = OPM_STATUS_KEYS[status];
  if (key === undefined) return status;
  const translated = t(key);
  return translated === key ? status : translated;
};
