import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { I18nProvider } from '@/shared/i18n/I18nContext';
import { formatCalendarDate, formatTimestamp } from '@/shared/lib/format';
import { StatusBoardCard } from '@/jarvis/cards/StatusBoardCard/StatusBoardCard';

describe('StatusBoardCard', () => {
  it('shows the diagnostic source/date and opens the finding in its well context', () => {
    const onOpen = vi.fn();
    const { container } = render(<I18nProvider><StatusBoardCard loading onOpen={onOpen} payload={{
      champion: { recorded: false }, last_run: { recorded: false },
      scenario: 'base', step: 96, date: '2015-01-01', data: 'model-z-base-run', generated_at: '2000-01-01T00:00:00Z',
      diagnostics: { recorded: true, reason: null, rows: [{ pattern: 'wct_rise_without_oil', name: 'water cut rising', well: '13', severity: 'warning', step: 96, date: '2015-01-01', window: [95, 96], source: 'base response' }] },
      violations: { recorded: true, run_id: 'run-fresh', reason: null, rows: [{ kind: 'WATERCUT_LIMIT_EXCEEDED', control_step: 96, well: '13', region: null, value: 0.97, detail: 'water cut limit exceeded', blocking: true }] }
    }} /></I18nProvider>);
    expect(screen.getByText(formatCalendarDate('ru', '2015-01-01'))).toBeTruthy();
    expect(container.querySelector('.jarvis-board-now')?.textContent).toContain('Базовый сценарий');
    expect(screen.getByText('Источник данных: Расчётные данные').getAttribute('title')).toBe('model-z-base-run');
    expect(container.querySelector('.jarvis-board-freshness')?.textContent).toContain(
      `Сформировано: ${formatTimestamp('ru', '2000-01-01T00:00:00Z')}`
    );
    expect(screen.getByText('base response')).toBeTruthy();
    expect(screen.getByText('интервал 95–96')).toBeTruthy();
    expect(screen.getByText('Обновляю сводку…')).toBeTruthy();
    expect(screen.getByText(/Данные могут устареть/)).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'Объяснить' }));
    expect(onOpen).toHaveBeenCalledWith({ workspace: 'decisions', view: 'rules', scenario: 'base', step: 96, well: '13' });
    fireEvent.click(screen.getByRole('button', { name: 'Показать нарушение' }));
    expect(onOpen).toHaveBeenCalledWith({ run_id: 'run-fresh', workspace: 'field', view: 'projection', step: 96, well: '13' });
  });

  it('reports diagnostics as unavailable instead of showing an empty alert list', () => {
    render(<I18nProvider><StatusBoardCard onOpen={() => undefined} payload={{
      champion: { recorded: false }, last_run: { recorded: false }, scenario: 'base', step: 0,
      date: null, data: '', alerts: [], diagnostics: { recorded: false, reason: 'scenario data missing' }
    }} /></I18nProvider>);
    expect(screen.getByText('scenario data missing')).toBeTruthy();
  });

  it('localizes known run and violation codes while preserving unknown codes', () => {
    const { unmount } = render(<I18nProvider><StatusBoardCard onOpen={() => undefined} payload={{
      champion: { recorded: false }, last_run: { recorded: true, run_id: 'run-1', status: 'verified' },
      scenario: 'base', step: 0, date: null, data: '',
      diagnostics: { recorded: true, rows: [] },
      violations: { recorded: true, run_id: 'run-1', rows: [{ kind: 'WATERCUT_LIMIT_EXCEEDED', control_step: null, well: null, region: null, detail: 'details', blocking: false }] }
    }} /></I18nProvider>);
    expect(screen.getByText('проверен на OPM')).toBeTruthy();
    expect(screen.getByText('Превышен лимит обводнённости')).toBeTruthy();
    unmount();

    window.localStorage.setItem('aios-lang', 'en');
    render(<I18nProvider><StatusBoardCard onOpen={() => undefined} payload={{
      champion: { recorded: false }, last_run: { recorded: true, run_id: 'run-1', status: 'verified' },
      scenario: 'base', step: 0, date: null, data: '',
      diagnostics: { recorded: true, rows: [] },
      violations: { recorded: true, run_id: 'run-1', rows: [
        { kind: 'WATERCUT_LIMIT_EXCEEDED', control_step: null, well: null, region: null, detail: 'details', blocking: false },
        { kind: 'EXTERNAL_KIND', control_step: null, well: null, region: null, detail: 'details', blocking: false }
      ] }
    }} /></I18nProvider>);
    expect(screen.getByText('verified by OPM')).toBeTruthy();
    expect(screen.getByText('Water cut limit exceeded')).toBeTruthy();
    expect(screen.getByText('EXTERNAL_KIND')).toBeTruthy();
  });

  it('localizes known diagnostic provenance and keeps its recorded value available', () => {
    const { container } = render(<I18nProvider><StatusBoardCard onOpen={() => undefined} payload={{
      champion: { recorded: false }, last_run: { recorded: false }, scenario: 'base', step: 0,
      date: null, data: '', diagnostics: { recorded: true, rows: [
        { pattern: 'p', name: 'finding', well: null, severity: 'info', step: null, date: null, window: null, source: 'model-z-base-run' }
      ] }, violations: { recorded: true, rows: [] }
    }} /></I18nProvider>);

    const source = container.querySelector('.jarvis-board-alerts small');
    expect(source?.textContent).toBe('Расчётные данные');
    expect(source?.getAttribute('title')).toBe('model-z-base-run');
  });

  it('uses the English diagnostic pattern label instead of the recorded Russian name', () => {
    window.localStorage.setItem('aios-lang', 'en');
    const { container } = render(<I18nProvider><StatusBoardCard onOpen={() => undefined} payload={{
      champion: { recorded: false }, last_run: { recorded: false }, scenario: 'base', step: 0,
      date: null, data: 'model-z-base-run', diagnostics: { recorded: true, rows: [
        { pattern: 'wct_rise_without_oil', name: 'Обводнённость растёт без прироста нефти', well: null, severity: 'warning', step: 0, date: null, window: null, source: 'model-z-base-run' }
      ] }, violations: { recorded: true, rows: [] }
    }} /></I18nProvider>);

    const name = container.querySelector('.jarvis-board-alerts li span');
    expect(name?.textContent).toBe('Water cut rises without oil gain');
    expect(name?.getAttribute('title')).toBe('wct_rise_without_oil');
  });

  it('localizes the known missing champion reason and retains its path', () => {
    render(<I18nProvider><StatusBoardCard onOpen={() => undefined} payload={{
      champion: { recorded: false, reason: 'there is no champion file /data/config/opm-champion.json: no pinned best OPM run is recorded' },
      last_run: { recorded: false }, scenario: 'base', step: 0, date: null, data: '',
      diagnostics: { recorded: true, rows: [] }, violations: { recorded: true, rows: [] }
    }} /></I18nProvider>);
    expect(screen.getByText('Файл закреплённого эталонного OPM-прогона не найден: /data/config/opm-champion.json')).toBeTruthy();
  });

  it('localizes the known empty runs directory reason and retains its path', () => {
    render(<I18nProvider><StatusBoardCard onOpen={() => undefined} payload={{
      champion: { recorded: false },
      last_run: { recorded: false, reason: 'the runs directory holds no run with a manifest: /data/out/runs; no calculation has been made yet' },
      scenario: 'base', step: 0, date: null, data: '',
      diagnostics: { recorded: true, rows: [] }, violations: { recorded: true, rows: [] }
    }} /></I18nProvider>);
    expect(screen.getByText('В каталоге /data/out/runs нет манифеста прогона; расчёты ещё не запускались.')).toBeTruthy();
  });

  it('does not offer a navigation action for a field-level violation without coordinates', () => {
    render(<I18nProvider><StatusBoardCard onOpen={() => undefined} payload={{
      champion: { recorded: false }, last_run: { recorded: false },
      scenario: 'base', step: 0, date: null, data: '',
      diagnostics: { recorded: true, rows: [] },
      violations: { recorded: true, run_id: 'run-1', rows: [{
        kind: 'MATERIAL_BALANCE_BROKEN', control_step: null, well: null, region: null,
        detail: 'field-level violation', blocking: true
      }] }
    }} /></I18nProvider>);
    expect(screen.getByText('Уровень поля')).toBeTruthy();
    expect(screen.queryByRole('button', { name: 'Показать нарушение' })).toBeNull();
  });
});
