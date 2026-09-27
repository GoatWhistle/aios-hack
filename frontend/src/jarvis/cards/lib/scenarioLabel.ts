import type { Translate } from '@/shared/i18n/I18nContext';

const SCENARIO_KEYS: Record<string, string> = {
  base: 'scenario.base',
  'whatif-injection-cut': 'scenario.injectionCut'
};

export const scenarioLabel = (scenario: string, t: Translate): string => {
  const key = SCENARIO_KEYS[scenario];
  return key === undefined ? scenario : t(`jarvis-cards.${key}`);
};
