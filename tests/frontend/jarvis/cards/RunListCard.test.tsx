import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { I18nProvider } from '@/shared/i18n/I18nContext';
import { RunListCard } from '@/jarvis/cards/RunListCard/RunListCard';

describe('RunListCard', () => {
  it('shows manifest modification dates and states when a date is unavailable', () => {
    const { container } = render(
      <I18nProvider>
        <RunListCard payload={{ rows: [
          { run_id: 'run-local', ts: '2026-09-27T01:00:00Z', status: 'verified', verified_npv: 1200, strategy: 'cma-es' },
          { run_id: 'run-registry', ts: '', status: 'unknown', verified_npv: null, strategy: 'external-search', scenario_role: 'external-role' }
        ], total: 2 }} />
      </I18nProvider>
    );

    const time = container.querySelector('time');
    expect(time?.getAttribute('dateTime')).toBe('2026-09-27T01:00:00Z');
    expect(time?.textContent).toMatch(/2026/);
    expect(screen.getByText('дата не записана')).toBeTruthy();
    expect(screen.getByText('проверен на OPM')).toBeTruthy();
    const strategy = screen.getByText('Поиск CMA-ES');
    expect(strategy.getAttribute('title')).toBe('cma-es');
    expect(screen.getByText('unknown')).toBeTruthy();
    expect(screen.getByText('external-search').getAttribute('title')).toBe('external-search');
    expect(screen.getByText('external-role').getAttribute('title')).toBe('external-role');
  });

  it('localizes recognized experimental screening strategies', () => {
    render(<I18nProvider><RunListCard payload={{ rows: [
      { run_id: 'run-screen', ts: '', status: 'searched', strategy: 'experimental-screen-model-top' }
    ], total: 1 }} /></I18nProvider>);

    expect(screen.getByText('Кандидат с высоким рангом модели').getAttribute('title')).toBe('experimental-screen-model-top');
  });
});
