import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { I18nProvider } from '@/shared/i18n/I18nContext';
import { WellComparisonCard } from '@/jarvis/cards/WellComparisonCard/WellComparisonCard';
import { readWellComparison } from '@/jarvis/cards/payloads/wellComparisonPayload';

describe('WellComparisonCard', () => {
  it('reads source-alignment metadata from decision evidence', () => {
    const parsed = readWellComparison({
      scenario: 'base', step: 0, date: '2007-01-01',
      a: { well: '1' }, b: { well: '10' },
      decision_evidence: { run_id: 'run-x', source_alignment: 'different-response', state_source_run_id: 'showcase-base' }
    });
    expect(parsed?.decision_evidence.source_alignment).toBe('different-response');
    expect(parsed?.decision_evidence.state_source_run_id).toBe('showcase-base');
  });

  it('warns when the decision response source cannot be checked', () => {
    render(
      <I18nProvider>
        <WellComparisonCard payload={{
          scenario: 'base', step: 0, date: '2007-01-01',
          a: { well: '1' }, b: { well: '10' },
          decision_evidence: { run_id: 'run-x', source_alignment: 'unverified', state_source_run_id: 'showcase-base' }
        }} />
      </I18nProvider>
    );

    expect(screen.getByRole('note').textContent).toContain('считайте их разными источниками');
  });

  it('shows comparable facts and explicitly says pairwise preference was not recorded', () => {
    render(
      <I18nProvider>
        <WellComparisonCard payload={{
          scenario: 'base', step: 0, date: '2007-01-01',
          a: { well: '1', role: 'PROD', availability: 'AVAILABLE', operating_status: 'OPEN', liquid_rate: 14, injection_rate: 0, watercut: 0.2, bhp: 50, setpoint: 45, npv_whole_horizon: 100 },
          b: { well: '10', role: 'PROD', availability: 'AVAILABLE', operating_status: 'OPEN', liquid_rate: 20, injection_rate: 0, watercut: 0.3, bhp: 52, setpoint: 50, npv_whole_horizon: 120 },
          deltas_b_minus_a: { liquid_rate: 6 },
          npv_provenance: 'model-z-base-run', npv_source_run_id: 'baseline-123',
          direct_connection: { measured: true, weight: 0.42, lag_months: 2, provenance: 'measured-connectivity' },
          decision_evidence: {
            run_id: 'run-x', source_alignment: 'different-response', state_source_run_id: 'showcase-base', pairwise_preference: 'not-recorded',
            well_constraints: { status: 'verified', outages: { '10': [{ well: '10', control_step_from: 0, control_step_to: 4 }] } },
            wells: {
              '1': { recorded: true, rule_facts: [{ level: 'WELL', agent: '1', entry: { rule: 'R2', decision: 'SET_LRAT' } }], final_events: [], group_allocations: [{ group_id: 'G1', injection_m3_per_day: 50 }], field_injection_limit_m3_per_day: 100 },
              '10': { recorded: true, rule_facts: [], final_events: [], group_allocations: [{ group_id: 'G1', injection_m3_per_day: 50 }], field_injection_limit_m3_per_day: 100 }
            }
          },
          alternative_status: 'state-comparison-only',
          comparison_note: 'State comparison only.'
        }} />
      </I18nProvider>
    );

    expect(screen.getByText('Скважина 1')).toBeTruthy();
    expect(screen.getByText('Скважина 10')).toBeTruthy();
    expect(document.querySelector('.jarvis-well-comparison-context')?.textContent).toContain('Базовый сценарий');
    expect(screen.getAllByText('Дебит жидкости')).toHaveLength(2);
    expect(screen.getAllByText('Забойное давление')).toHaveLength(2);
    expect(screen.getAllByText('ЧДД за весь горизонт')).toHaveLength(2);
    expect(screen.getAllByText('добывающая')).toHaveLength(2);
    expect(screen.getAllByText('доступна')).toHaveLength(2);
    expect(screen.getAllByText('работает')).toHaveLength(2);
    expect(screen.getByText('Попарное предпочтение алгоритма не записано')).toBeTruthy();
    const npvSource = screen.getByText('Источник ЧДД: Расчётные данные · baseline-123');
    expect(npvSource.getAttribute('title')).toBe('model-z-base-run');
    const directLink = screen.getByTitle('measured-connectivity');
    expect(directLink.textContent).toContain('Расчётные данные');
    expect(directLink.getAttribute('title')).toBe('measured-connectivity');
    expect(screen.getByRole('note').textContent).toContain('showcase-base');
    expect(screen.getByRole('note').textContent).toContain('отдельного прогона run-x');
    expect(screen.getByText(/не доказывает причину выбора/)).toBeTruthy();
    expect(screen.getByText('Скважина/1 · Разгон чистых, придушивание обводнённых (R2) → Задать дебит жидкости')).toBeTruthy();
    expect(screen.getAllByText(/лимит закачки поля: 100/)).toHaveLength(1);
    expect(screen.getAllByText(/G1: 50 м³\/сут/)).toHaveLength(1);
    expect(screen.getAllByText(/запись журнала по скважине 1, 10/)).toHaveLength(2);
    expect(screen.getByText(/Ограничения проверены по хешу прогона/)).toBeTruthy();
    expect(screen.getByText(/остановка на шагах 0–4/)).toBeTruthy();
    expect(screen.getByText('14 м³/сут')).toBeTruthy();
    expect(screen.getByText('50 бар')).toBeTruthy();
    expect(screen.getByText(/100 руб\./)).toBeTruthy();
  });

  it('preserves an unknown well-constraint status instead of displaying a translation key', () => {
    render(<I18nProvider><WellComparisonCard payload={{
      scenario: 'base', step: 0, date: '2007-01-01', a: { well: '1' }, b: { well: '10' },
      decision_evidence: { well_constraints: { status: 'external-status', outages: {} } }
    }} /></I18nProvider>);
    expect(screen.getByText('external-status')).toBeTruthy();
  });

  it('keeps unknown recorded-decision codes visible', () => {
    render(<I18nProvider><WellComparisonCard payload={{
      scenario: 'base', step: 0, date: '2007-01-01', a: { well: '1' }, b: { well: '10' },
      decision_evidence: { wells: { '1': { recorded: true, rule_facts: [{
        level: 'CUSTOM_LEVEL', agent: 'ExternalAgent', entry: { rule: 'R99', decision: 'CUSTOM_ACTION' }
      }] } } }
    }} /></I18nProvider>);
    expect(screen.getByText('CUSTOM_LEVEL/ExternalAgent · R99 → CUSTOM_ACTION')).toBeTruthy();
  });
});
