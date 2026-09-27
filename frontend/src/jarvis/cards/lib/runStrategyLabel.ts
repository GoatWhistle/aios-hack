import type { Translate } from '@/shared/i18n/I18nContext';
import { translationOrRaw } from '@/jarvis/cards/lib/translationFallback';

const STRATEGIES: Record<string, string> = {
  'cma-es': 'cmaEs',
  'cmaes-restart': 'cmaEsRestart',
  'lambda-connectivity-transfer': 'connectivityTransfer',
  'baseline-neighborhood': 'baselineNeighborhood',
  'original-baseline': 'originalBaseline'
};

const SCREEN_ARMS = new Set([
  'hybrid-top', 'trajectory-top', 'direct-head-control', 'model-top', 'unranked-control'
]);

export const runStrategyLabel = (strategy: string, t: Translate): string => {
  const key = STRATEGIES[strategy];
  if (key !== undefined) return translationOrRaw(`jarvis-cards.runStrategy.${key}`, strategy, t);
  const prefix = 'experimental-screen-';
  if (strategy.startsWith(prefix)) {
    const arm = strategy.slice(prefix.length);
    if (SCREEN_ARMS.has(arm)) {
      return translationOrRaw(`jarvis-cards.runStrategy.screen.${arm}`, strategy, t);
    }
  }
  return strategy;
};
