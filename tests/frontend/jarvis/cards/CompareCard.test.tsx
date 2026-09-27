import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { I18nProvider } from '@/shared/i18n/I18nContext';
import { CompareCard } from '@/jarvis/cards/CompareCard/CompareCard';

describe('CompareCard OPM output differences', () => {
  it('localizes comparison signature field names while preserving the causal limitation', () => {
    const payload = {
      a: { id: 'run-a', status: {}, constraints: {} },
      b: { id: 'run-b', status: {}, constraints: {} },
      comparability: {
        status: 'incomparable',
        note: 'Conditions differ on: constraints. The NPV delta is arithmetic.',
        missing_fields: [], mismatched_fields: ['constraints', 'future_field']
      },
      economic_breakdown: { recorded: false },
      production_injection: { recorded: false },
      conclusion_markdown: null
    };
    window.localStorage.setItem('aios-lang', 'ru');
    const view = render(<I18nProvider><CompareCard payload={payload} /></I18nProvider>);
    expect(screen.getByText(/Условия различаются по полям: ограничения, future_field/)).toBeTruthy();
    expect(screen.getByText(/не причинный вклад отдельного действия/)).toBeTruthy();

    window.localStorage.setItem('aios-lang', 'en');
    view.unmount();
    render(<I18nProvider><CompareCard payload={payload} /></I18nProvider>);
    expect(screen.getByText(/Conditions differ for: constraints, future_field/)).toBeTruthy();
    window.localStorage.setItem('aios-lang', 'ru');
  });

  it('localizes known constraint groups and labels their counts in Russian and English', () => {
    const payload = {
      a: { id: 'run-a', npv: 10, status: {}, constraints: { injection_limits: 2, well_outages: 1 } },
      b: { id: 'run-b', npv: 12, status: {}, constraints: { injection_limits: 3, well_outages: 0, custom_rule: 4 } },
      delta_npv: 2,
      economic_breakdown: { recorded: false, deltas_b_minus_a: null, reason: 'one or both runs have no recorded economics/npv-table.json' },
      production_injection: { recorded: false, reason: 'one or both runs have no observation/<schedule_hash>/response.json', matched_rows: 0, unmatched_rows: null, totals_delta_b_minus_a: null, top_diff_wells_steps: [] },
      comparison_reason: 'no-comparison: run run-b has no comparison.json file, so the breakdown of the difference by well is unknown',
      conclusion_markdown: null
    };

    window.localStorage.setItem('aios-lang', 'ru');
    const view = render(<I18nProvider><CompareCard payload={payload} /></I18nProvider>);
    expect(screen.getAllByText('Лимиты закачки')).toHaveLength(2);
    expect(screen.getByText('условий: 2')).toBeTruthy();
    expect(screen.getByText('Остановки скважин')).toBeTruthy();
    expect(screen.getByText('В одном или обоих прогонах нет записанного файла economics/npv-table.json.')).toBeTruthy();
    expect(screen.getByText('Для одного или обоих прогонов нет записанного OPM-ответа.')).toBeTruthy();
    expect(screen.getByText('Для прогона run-b нет файла comparison.json, поэтому разложение разницы по скважинам недоступно.')).toBeTruthy();

    window.localStorage.setItem('aios-lang', 'en');
    view.unmount();
    render(<I18nProvider><CompareCard payload={payload} /></I18nProvider>);
    expect(screen.getAllByText('Injection limits')).toHaveLength(2);
    expect(screen.getByText('conditions: 3')).toBeTruthy();
    expect(screen.getByText('custom_rule')).toBeTruthy();
    expect(screen.getByText('One or both runs have no recorded economics/npv-table.json.')).toBeTruthy();
    expect(screen.getByText('One or both runs have no recorded OPM response file.')).toBeTruthy();
    expect(screen.getByText('Run run-b has no comparison.json file, so the per-well breakdown is unavailable.')).toBeTruthy();
    window.localStorage.setItem('aios-lang', 'ru');
  });

  it('labels NPV sources separately and explains when their delta is unavailable', () => {
    render(<I18nProvider><CompareCard payload={{
      a: { id: 'run-a', npv: 10, npv_basis: 'predicted', status: { opm_status: 'OK' }, constraints: {} },
      b: { id: 'run-b', npv: 12, npv_basis: 'verified', status: { opm_status: 'FUTURE_STATUS' }, constraints: {} },
      delta_npv: null, delta_npv_reason: 'sources differ',
      economic_breakdown: { recorded: false, deltas_b_minus_a: null, reason: 'missing' },
      production_injection: { recorded: false, reason: 'missing', matched_rows: 0, unmatched_rows: null, totals_delta_b_minus_a: null, top_diff_wells_steps: [] },
      top_diff_wells: [{ well: 'W2', delta: 5 }],
      conclusion_markdown: null
    }} /></I18nProvider>);

    expect(screen.getByText('Прогноз ЧДД суррогата')).toBeTruthy();
    expect(screen.getByText('ЧДД после OPM')).toBeTruthy();
    expect(screen.getByText(/источники различаются/)).toBeTruthy();
    expect(screen.getByText('10 руб.')).toBeTruthy();
    expect(screen.getByText('12 руб.')).toBeTruthy();
    expect(screen.getByText('расчёт завершён')).toBeTruthy();
    expect(screen.getByText('FUTURE_STATUS')).toBeTruthy();
    expect(screen.getByText('5 руб.')).toBeTruthy();
  });

  it('preserves an unfamiliar NPV source code rather than dropping it', () => {
    render(<I18nProvider><CompareCard payload={{
      a: { id: 'run-a', npv: 10, npv_basis: 'custom-source', status: {}, constraints: {} },
      b: { id: 'run-b', npv: 12, status: {}, constraints: {} },
      economic_breakdown: { recorded: false },
      production_injection: { recorded: false },
      conclusion_markdown: null
    }} /></I18nProvider>);
    expect(screen.getByText('custom-source')).toBeTruthy();
  });

  it('localizes recorded economic line item keys and keeps their RUB units', () => {
    const payload = {
      a: { id: 'run-a', npv: 10, status: {}, constraints: {} },
      b: { id: 'run-b', npv: 12, status: {}, constraints: {} },
      delta_npv: 2,
      economic_breakdown: { recorded: true, deltas_b_minus_a: { revenue: 40, discounted_fcf: 20, df: 0.1 }, reason: null },
      production_injection: { recorded: false, reason: 'missing', matched_rows: 0, unmatched_rows: null, totals_delta_b_minus_a: null, top_diff_wells_steps: [] },
      conclusion_markdown: null
    };

    window.localStorage.setItem('aios-lang', 'ru');
    const view = render(<I18nProvider><CompareCard payload={payload} /></I18nProvider>);
    expect(screen.getByText('Выручка')).toBeTruthy();
    expect(screen.getByText('Дисконтированный денежный поток')).toBeTruthy();
    expect(screen.getByText('40 руб.')).toBeTruthy();
    expect(screen.getByText('20 руб.')).toBeTruthy();
    expect(screen.queryByText('revenue')).toBeNull();

    window.localStorage.setItem('aios-lang', 'en');
    view.unmount();
    render(<I18nProvider><CompareCard payload={payload} /></I18nProvider>);
    expect(screen.getByText('Revenue')).toBeTruthy();
    expect(screen.getByText('Discounted free cash flow')).toBeTruthy();
    expect(screen.getByText('40 RUB')).toBeTruthy();
    window.localStorage.setItem('aios-lang', 'ru');
  });

  it('opens the compared run at a differing well and control step', () => {
    const onOpen = vi.fn();
    render(<I18nProvider><CompareCard payload={{
      a: { id: 'run-a', npv: 1, status: {}, constraints: {} },
      b: { id: 'run-b', npv: 2, status: {}, constraints: {} },
      delta_npv: 1,
      economic_breakdown: { recorded: false, deltas_b_minus_a: null, reason: 'missing' },
      production_injection: {
        recorded: true, reason: null, matched_rows: 1, unmatched_rows: 0,
        totals_delta_b_minus_a: { oil_mass_delta: 5, injection_volume_delta: 3 },
        top_diff_wells_steps: [{ well: 'W7', control_step: 12, oil_mass_delta_b_minus_a: 4, injection_volume_delta_b_minus_a: 2 }]
      },
      conclusion_markdown: '# Заключение по сравнению\n\nСопоставимость не подтверждена.'
    }} action={{ run_id: 'run-b', scenario: 'case' }} onOpen={onOpen} /></I18nProvider>);

    fireEvent.click(screen.getByRole('button', { name: 'Открыть это место' }));

    expect(screen.getByText('Сравнительное заключение')).toBeTruthy();
    expect(screen.getByText('5 кг')).toBeTruthy();
    expect(screen.getByText('3 м³')).toBeTruthy();

    expect(onOpen).toHaveBeenCalledWith({
      workspace: 'field', view: 'projection', run_id: 'run-b', scenario: 'case', well: 'W7', step: 12
    });
  });
});
