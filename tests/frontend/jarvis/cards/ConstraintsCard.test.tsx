import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { ConstraintsCard } from '@/jarvis/cards/ConstraintsCard/ConstraintsCard';
import { I18nProvider } from '@/shared/i18n/I18nContext';

describe('ConstraintsCard', () => {
  it('localizes known fields, groups, and provenance labels', () => {
    render(
      <I18nProvider>
        <ConstraintsCard payload={{
          case: 'competition',
          items: [{
            key: 'external_water_m3_per_day', group: 'infrastructure',
            value: 12, unit: 'm3/day', source: 'organizer'
          }]
        }} />
      </I18nProvider>
    );

    expect(screen.getByText('Инфраструктура')).toBeTruthy();
    expect(screen.getByText('Лимит внешней воды')).toBeTruthy();
    expect(screen.getByText('м³/сут')).toBeTruthy();
    expect(screen.getByText('Требование организатора')).toBeTruthy();
  });

  it('labels a numeric constraint whose unit is missing instead of silently omitting it', () => {
    render(
      <I18nProvider>
        <ConstraintsCard payload={{
          case: 'external',
          items: [{ key: 'custom_numeric_limit', group: 'limits', value: 5, unit: null, source: null }]
        }} />
      </I18nProvider>
    );

    expect(screen.getByText('custom_numeric_limit')).toBeTruthy();
    expect(screen.getByText('единица не указана')).toBeTruthy();
  });
});
