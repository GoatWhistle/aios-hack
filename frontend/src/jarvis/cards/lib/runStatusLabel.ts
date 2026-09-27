import type { Translate } from '@/shared/i18n/I18nContext';

const RUN_STATUS_KEYS: Readonly<Record<string, string>> = {
  searched: 'jarvis-cards.runState.searched',
  verified: 'jarvis-cards.runState.verified',
  rejected: 'jarvis-cards.runState.rejected',
  ready_to_submit: 'jarvis-cards.runState.ready_to_submit'
};

export const runStatusLabel = (status: string | null, t: Translate): string => {
  if (status === null) return '—';
  const key = RUN_STATUS_KEYS[status];
  if (key === undefined) return status;
  const translated = t(key);
  return translated === key ? status : translated;
};
