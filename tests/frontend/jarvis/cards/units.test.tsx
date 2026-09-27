import { render } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import { I18nProvider } from '@/shared/i18n/I18nContext';
import { MetricCard } from '@/jarvis/cards/MetricCard/MetricCard';
import { RunCard } from '@/jarvis/cards/RunCard/RunCard';
import { SeriesCard } from '@/jarvis/cards/SeriesCard/SeriesCard';
import { WellCard } from '@/jarvis/cards/WellCard/WellCard';
import { WellListCard } from '@/jarvis/cards/WellListCard/WellListCard';

describe('card quantity units', () => {
  afterEach(() => window.localStorage.clear());

  it('shows metric units on values and deltas', () => {
    window.localStorage.setItem('aios-lang', 'ru');
    const { container } = render(
      <I18nProvider>
        <MetricCard payload={{ metrics: [{
          id: 'production', label: 'Добыча', value: 12.5, unit: 'm3/day',
          delta: 1.5, spark: []
        }] }} />
      </I18nProvider>
    );

    expect(container.querySelector('.jarvis-metric-unit')?.textContent).toBe('м³/сут');
    expect(container.textContent).toContain('1,5 м³/сут');
  });

  it('marks missing metric units on both values and deltas', () => {
    window.localStorage.setItem('aios-lang', 'ru');
    const { container } = render(
      <I18nProvider>
        <MetricCard payload={{ metrics: [{
          id: 'untyped', label: 'Показатель', value: 12.5, unit: '', delta: 1.5, spark: []
        }] }} />
      </I18nProvider>
    );

    expect(container.textContent).toContain('12,5единица не указана');
    expect(container.textContent).toContain('1,5 единица не указана');
  });

  it('shows well snapshot values with their dimensions', () => {
    window.localStorage.setItem('aios-lang', 'ru');
    const { container } = render(
      <I18nProvider>
        <WellCard payload={{
          well: '13', step: 96, date: '2015-01-01', role: 'PROD', availability: 'AVAILABLE', operating_status: 'OPEN',
          liquid_rate: 12.5, injection_rate: 3, watercut: 0.5, bhp: 91,
          setpoint: 10, npv: 1200, spark: []
        }} />
      </I18nProvider>
    );

    expect(container.textContent).toContain('12,5 м³/сут');
    expect(container.textContent).toContain('шаг 96 · 1 янв. 2015 г.');
    expect(container.textContent).toContain('91 бар');
    expect(container.textContent).toContain('10 м³/сут');
    expect(container.textContent).toContain('1 200 руб.');
  });

  it('shows the dimension next to every ranked well value', () => {
    window.localStorage.setItem('aios-lang', 'ru');
    const { container } = render(
      <I18nProvider>
        <WellListCard payload={{
          by: 'liquid_rate', unit: 'm3/day', period: 'control_step', step: 96, date: '2015-01-01', total_count: 12, rows: [
            { well: '13', value: 12.5, share: 0.2 }
          ]
        }} />
      </I18nProvider>
    );

    expect(container.textContent).toContain('12,5 м³/сут');
    expect(container.textContent).toContain('20 %');
    expect(container.textContent).toContain('Шаг 96 · 1 янв. 2015 г.');
    expect(container.textContent).toContain('Показано 1 из 12 скважин');
  });

  it.each([
    ['ru', 'liquid_rate', 'Дебит жидкости'],
    ['en', 'liquid_rate', 'Liquid rate'],
    ['ru', 'injection_rate', 'Дебит закачки'],
    ['en', 'watercut', 'Water cut'],
    ['ru', 'npv', 'ЧДД за весь горизонт']
  ])('localizes the ranked metric label (%s, %s)', (lang, metric, label) => {
    window.localStorage.setItem('aios-lang', lang);
    const unit = metric === 'npv' ? 'RUB' : metric === 'watercut' ? 'fraction' : 'm3/day';
    const { container } = render(
      <I18nProvider>
        <WellListCard payload={{
          by: metric, unit,
          period: metric === 'npv' ? 'whole_horizon' : 'control_step',
          step: metric === 'npv' ? null : 96,
          date: metric === 'npv' ? null : '2015-01-01',
          rows: [{ well: '13', value: 12.5, share: 0.2 }]
        }} />
      </I18nProvider>
    );

    expect(container.textContent).toContain(label);
    expect(container.textContent).not.toContain(metric);
    if (metric === 'npv') {
      expect(container.textContent).toContain(lang === 'ru' ? 'Весь горизонт прогноза' : 'Whole forecast horizon');
    }
  });

  it('shows the latest series value with its unit', () => {
    window.localStorage.setItem('aios-lang', 'ru');
    const { container } = render(
      <I18nProvider>
        <SeriesCard payload={{
          metric: 'liquid_rate', unit: 'm3/day', window: null,
          rows: [
            { step: 0, date: '2007-01-01', value: 10 },
            { step: 1, date: '2007-02-01', value: 12.5 }
          ]
        }} />
      </I18nProvider>
    );

    expect(container.textContent).toContain('12,5 м³/сут');
    expect(container.querySelector('svg title')?.textContent).toBe('Дебит жидкости');
  });

  it('shows run NPV with currency units', () => {
    window.localStorage.setItem('aios-lang', 'en');
    const { container } = render(
      <I18nProvider>
        <RunCard payload={{
          run_id: 'run-1', ts: '2026-09-27T01:00:00Z', status: 'verified', predicted_npv: 1000,
          verified_npv: 900, conclusion_markdown: null
        }} />
      </I18nProvider>
    );

    expect(container.textContent).toContain('1,000 RUB');
    expect(container.textContent).toContain('900 RUB');
    expect(container.querySelector('time')?.getAttribute('dateTime')).toBe('2026-09-27T01:00:00Z');
    expect(container.querySelector('time')?.textContent).toContain('2026');
  });

  it('states when a run manifest date is unavailable', () => {
    const { container } = render(
      <I18nProvider>
        <RunCard payload={{ run_id: 'run-registry', status: 'unknown' }} />
      </I18nProvider>
    );

    expect(container.textContent).toContain('Манифест обновлён: дата не записана');
  });
});
