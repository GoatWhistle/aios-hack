import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { I18nProvider } from '@/shared/i18n/I18nContext';
import { PatternCard } from '@/jarvis/cards/PatternCard/PatternCard';

describe('PatternCard measurement units', () => {
  it('shows pressure, rate, and watercut units for detector inputs', () => {
    render(<I18nProvider><PatternCard payload={{
      pattern_id: 'pressure_drop_at_high_rates',
      name: 'Pressure drop at high rates', well: 'W1', severity: 'warning',
      window: { from_step: 2, to_step: 3 },
      inputs: { bhp_prev: 100, bhp_curr: 50, liquid_rate: 12 }
    }} /></I18nProvider>);

    expect(screen.getByText('100 бар')).toBeTruthy();
    expect(screen.getByText('50 бар')).toBeTruthy();
    expect(screen.getByText('12 м³/сут')).toBeTruthy();
    expect(screen.getByText('Предыдущее забойное давление')).toBeTruthy();
    expect(screen.getByText(/предупреждение/)).toBeTruthy();
  });

  it('formats watercut inputs as percentages', () => {
    render(<I18nProvider><PatternCard payload={{
      pattern_id: 'wct_rise_without_oil',
      name: 'Watercut rise without oil', well: 'W2', severity: 'warning',
      step: 1, date: '2007-02-01', window: null,
      inputs: { watercut_prev: 0.2, watercut_curr: 0.4 }
    }} /></I18nProvider>);

    expect(screen.getByText(/20\s*%/)).toBeTruthy();
    expect(screen.getByText(/40\s*%/)).toBeTruthy();
    expect(screen.getByText(/шаг 1/)).toBeTruthy();
  });

  it('reads the backend array window and shows recorded step dates', () => {
    const { container } = render(<I18nProvider><PatternCard payload={{
      pattern_id: 'injection_without_response', name: 'Injection without response',
      well: 'W3', severity: 'warning', step: 13, date: '2008-02-01',
      window: [12, 13], window_dates: ['2008-01-01', '2008-02-01'],
      inputs: { injection_total: 120, production_delta: 0 }
    }} /></I18nProvider>);

    expect(container.textContent).toContain('12–13');
    expect(container.textContent).toContain('2008');
    expect(container.textContent).toContain('шаг 13');
    expect(container.textContent).toContain('Сумма значений дебита закачки');
    expect(container.textContent).toContain('м³/сут × число точек');
    expect(container.textContent).toContain('Изменение добычи поля');
  });

  it('does not display an unexplained numeric input without a unit label', () => {
    render(<I18nProvider><PatternCard payload={{
      pattern_id: 'future_pattern', name: 'Future finding', well: 'W4', severity: 'unknown',
      inputs: { unknown_measure: 4 }
    }} /></I18nProvider>);

    expect(screen.getByText('unknown_measure')).toBeTruthy();
    expect(screen.getByText(/4.*единица не указана/)).toBeTruthy();
  });
});
