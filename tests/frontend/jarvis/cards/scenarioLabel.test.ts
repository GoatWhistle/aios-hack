import { describe, expect, it } from 'vitest';
import { dictionaries } from '@/shared/i18n/dictionaries';
import { scenarioLabel } from '@/jarvis/cards/lib/scenarioLabel';

describe('scenarioLabel', () => {
  it.each([
    ['ru', 'base', 'Базовый сценарий'],
    ['ru', 'whatif-injection-cut', 'Сокращение закачки'],
    ['en', 'base', 'Base scenario'],
    ['en', 'whatif-injection-cut', 'Injection cut']
  ] as const)('localizes %s scenario %s', (lang, scenario, expected) => {
    const t = (key: string) => dictionaries[lang][key] ?? key;
    expect(scenarioLabel(scenario, t)).toBe(expected);
  });

  it('keeps unknown scenario identifiers visible', () => {
    expect(scenarioLabel('external-scenario-v3', (key) => key)).toBe('external-scenario-v3');
  });
});
