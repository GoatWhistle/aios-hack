import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { I18nProvider } from '@/shared/i18n/I18nContext';
import { RunStatusCard } from '@/jarvis/cards/RunStatusCard/RunStatusCard';

describe('RunStatusCard', () => {
  it('opens a recorded violation at its well and step in the selected run', () => {
    const onOpen = vi.fn();
    render(<I18nProvider><RunStatusCard onOpen={onOpen} payload={{
      run_id: 'run-1', status: 'rejected',
      acceptance: { verdict: 'rejected', opm_status: 'OK', sound: false, blocking_violations: 1, dynamic_violations: 1 },
      violation_locations: { recorded: true, total: 1, truncated: false, reason: null, rows: [
        { kind: 'WATERCUT_LIMIT_EXCEEDED', control_step: 4, well: 'W1', region: null, value: 0.97, detail: 'limit exceeded', blocking: true }
      ] }
    }} /></I18nProvider>);

    fireEvent.click(screen.getByRole('button', { name: 'Открыть это место' }));

    expect(screen.getByText('run-1 · отклонён')).toBeTruthy();
    expect(screen.getByText(/OPM: расчёт завершён · Проверки для сдачи: нет/)).toBeTruthy();
    expect(onOpen).toHaveBeenCalledWith({
      workspace: 'field', view: 'projection', run_id: 'run-1', well: 'W1', step: 4
    });
  });

  it('formats recorded violation values with units derived from their kind', () => {
    render(<I18nProvider><RunStatusCard onOpen={vi.fn()} payload={{
      run_id: 'run-3', status: 'rejected',
      violation_locations: { recorded: true, total: 3, truncated: false, reason: null, rows: [
        { kind: 'WATERCUT_LIMIT_EXCEEDED', control_step: 4, well: null, region: null, value: 0.97, detail: 'watercut limit exceeded', blocking: true },
        { kind: 'BHP_ABOVE_INJECTOR_LIMIT', control_step: 5, well: 'W2', region: null, value: 315, detail: 'pressure limit exceeded', blocking: true },
        { kind: 'CUSTOM_RULE_BREACH', control_step: 6, well: 'W3', region: null, value: null, detail: 'custom rule failed', blocking: false }
      ] }
    }} /></I18nProvider>);

    expect(screen.getByText(/watercut limit exceeded.*97\s?%/)).toBeTruthy();
    expect(screen.getByText(/pressure limit exceeded.*315 бар/)).toBeTruthy();
    expect(screen.getByText('Превышен лимит обводнённости')).toBeTruthy();
    expect(screen.getByText('CUSTOM_RULE_BREACH')).toBeTruthy();
  });

  it('localizes known recorded violation details and preserves unknown text', () => {
    render(<I18nProvider><RunStatusCard onOpen={vi.fn()} payload={{
      run_id: 'run-4', status: 'rejected',
      violation_locations: { recorded: true, total: 3, truncated: false, rows: [
        { kind: 'OPEN_WITHOUT_FLOW', control_step: 1, well: '71', region: null, value: 25, detail: 'the schedule keeps the well open with setpoint 25 m3/day, the response gives a zero rate; control mode SHUT', blocking: true },
        { kind: 'BHP_LIMITED_WITHOUT_UNDERSHOOT', control_step: 2, well: '76', region: null, value: 0.99, detail: 'BHP_LIMITED mode while the target is reached: a pressure limit is claimed, but there is no shortfall', blocking: true },
        { kind: 'EXTERNAL_KIND', control_step: 3, well: '77', region: null, value: null, detail: 'external detail', blocking: false }
      ] }
    }} /></I18nProvider>);
    expect(screen.getByText(/В расписании скважина открыта с уставкой 25 м³\/сут.*режим управления: остановка/)).toBeTruthy();
    expect(screen.getByText(/Указан режим BHP_LIMITED, хотя цель достигнута: недобора, который можно было бы объяснить давлением, нет.*99/)).toBeTruthy();
    expect(screen.getByText('external detail')).toBeTruthy();
  });

  it('shows unchecked constraints and keeps surrogate and verified NPV sources separate', () => {
    render(<I18nProvider><RunStatusCard onOpen={vi.fn()} payload={{
      run_id: 'run-2', status: 'verified',
      acceptance: {
        verdict: 'unknown', opm_status: 'OK', sound: true,
        blocking_violations: 0, dynamic_violations: 0,
        unverified_reason: 'water limits are not set',
        npv_sources: {
          predicted: { value: 1200, source: 'surrogate prediction' },
          verified: { value: 1100, source: 'OPM verification' }
        }
      },
      constraints: { recorded: true, unavailable_reason: null, checks: [
        { constraint: 'watercut_limits', status: 'not_set', n_violations: null, blocking: false, enforcement: 'diagnostic', detail: 'watercut limit is not configured' },
        { constraint: 'custom_constraint', status: 'checked', n_violations: 0, blocking: false, enforcement: 'external-mode', detail: 'custom check' }
      ] },
      violation_locations: { recorded: false, rows: [], total: null, truncated: false, reason: null }
    }} /></I18nProvider>);

    expect(screen.getByText('Лимиты обводнённости')).toBeTruthy();
    expect(screen.getByText('custom_constraint')).toBeTruthy();
    expect(screen.getByText(/режим: только диагностика/)).toBeTruthy();
    expect(screen.getByText(/режим: external-mode/)).toBeTruthy();
    expect(screen.getAllByText(/не задано/)).toHaveLength(2);
    expect(screen.getByText('Ограничение не задано или необходимые данные отсутствуют; проверка не выполнялась.').getAttribute('title'))
      .toBe('watercut limit is not configured');
    expect(screen.getAllByText(/блокирует: нет/)).toHaveLength(2);
    expect(screen.getByText(/Прогноз ЧДД/)).toBeTruthy();
    expect(screen.getByText(/ЧДД после OPM/)).toBeTruthy();
    expect(screen.getByText('прогноз суррогатной модели').getAttribute('title')).toBe('surrogate prediction');
    expect(screen.getByText('проверка OPM').getAttribute('title')).toBe('OPM verification');
    expect(screen.getByText(/1.?200 руб\./)).toBeTruthy();
    expect(screen.getByText(/1.?100 руб\./)).toBeTruthy();
  });

  it('localizes checked constraint details from recorded English reports and retains their source text', () => {
    const reportDetail = 'reinjection fraction 1.0, lag 0 steps, external inflow 0.0 m3/day: injection checked against the water balance on 224 steps';
    render(<I18nProvider><RunStatusCard onOpen={vi.fn()} payload={{
      run_id: 'run-5', status: 'verified',
      constraints: { recorded: true, checks: [
        { constraint: 'liquid_limits', status: 'checked', blocking: false, n_violations: 0, enforcement: null, detail: 'the upper limit of total liquid production by year is set for years 2017 and checked step by step' },
        { constraint: 'infrastructure.water_supply', status: 'checked', blocking: false, n_violations: 0, enforcement: null, detail: reportDetail },
        { constraint: 'well_outages', status: 'checked', blocking: false, n_violations: 0, enforcement: null, detail: 'outage windows 1: the response was checked for zero rate and zero injection inside each window' },
        { constraint: 'well_outages (static)', status: 'checked', blocking: false, n_violations: 0, enforcement: null, detail: 'outage windows 1: schedule events were checked for positive setpoints and OPEN inside a window' },
        { constraint: 'infrastructure.bhp_limits', status: 'checked', blocking: false, n_violations: 0, enforcement: null, detail: 'bottomhole pressure corridor 50.0...300.0 bar: organizer limits' },
        { constraint: 'infrastructure.compensation', status: 'checked', blocking: false, n_violations: 0, enforcement: null, detail: 'compensation corridor 0.85...1.15, mode diagnostic: C(k) = injection / withdrawal checked over the field on 224 steps under surface conditions; the formation volume factors B_o/B_w were not supplied to the validator: C(k) is computed under surface conditions, conversion to reservoir conditions was not performed' },
        { constraint: 'infrastructure.compensation_scope', status: 'checked', blocking: false, n_violations: 0, enforcement: null, detail: "infrastructure.compensation_scope = 'field_and_groups': the corridor 0.85...1.15 was checked per group under surface conditions, split cf41ef7f9b79301a6f98f6f5dec9a67050e361fad2f73021352bcc268dc87e49 of 1 groups, 224 step-group pairs; the formation volume factors B_o/B_w were not supplied to the validator: C(k) is computed under surface conditions, conversion to reservoir conditions was not performed" }
      ] },
      violation_locations: { recorded: false, rows: [], total: null, truncated: false }
    }} /></I18nProvider>);
    expect(screen.getByText('Годовой лимит проверялся на каждом шаге для годов 2017.')).toBeTruthy();
    const waterBalance = screen.getByText(/Баланс воды проверен на 224 шагах/);
    expect(waterBalance.textContent).toContain('доля возврата 1');
    expect(waterBalance.getAttribute('title')).toBe(reportDetail);
    expect(screen.getByText(/В отклике проверено отсутствие добычи и закачки в 1 окнах простоя/)).toBeTruthy();
    expect(screen.getByText(/В расписании проверены открытый статус и положительные уставки/)).toBeTruthy();
    expect(screen.getByText('Пределы забойного давления проверены в диапазоне 50–300 бар.')).toBeTruthy();
    expect(screen.getByText(/Компенсация C\(k\) = закачка \/ отбор проверена по полю на 224 шагах.*поверхностных условиях/)).toBeTruthy();
    expect(screen.getByText(/Компенсация проверена в коридоре 0,85–1,15 по 1 группам и 224 парам шаг-группа/)).toBeTruthy();
  });

  it('shows an unknown acceptance code instead of an untranslated dictionary key', () => {
    render(<I18nProvider><RunStatusCard onOpen={vi.fn()} payload={{
      run_id: 'run-custom', acceptance: { verdict: 'external-verdict' }
    }} /></I18nProvider>);
    expect(screen.getByText('external-verdict')).toBeTruthy();
  });

  it('localizes fixed missing-artifact reasons and preserves external reason text', () => {
    render(<I18nProvider><RunStatusCard onOpen={vi.fn()} payload={{
      run_id: 'run-reason',
      constraints: { recorded: false, unavailable_reason: 'there is no constraints report: the file validation/constraints_report.json is not recorded' },
      violation_locations: { recorded: false, reason: 'provider supplied detail' }
    }} /></I18nProvider>);

    expect(screen.getByText('Файл отчёта ограничений не записан.')).toBeTruthy();
    expect(screen.getByText('provider supplied detail')).toBeTruthy();
  });
});
