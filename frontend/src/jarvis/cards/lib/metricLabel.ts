const METRIC_LABEL_KEYS: Readonly<Record<string, string>> = {
  npv: 'wholeHorizonNpv',
  watercut: 'watercut',
  liquid_rate: 'liquidRate',
  injection_rate: 'injectionRate',
  bhp: 'bhp'
};

export const metricLabelKey = (metric: string): string | null =>
  METRIC_LABEL_KEYS[metric] ?? null;
