import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { I18nProvider } from '@/shared/i18n/I18nContext';
import { WellCard } from '@/jarvis/cards/WellCard';

const payload = {
  well: '13', step: 96, date: '2015-01-01', role: 'PROD', availability: 'AVAILABLE',
  operating_status: 'OPEN', liquid_rate: 70, injection_rate: 0, watercut: 0.5,
  bhp: 91, setpoint: 50, npv: -20491675, npv_provenance: 'model-z-base-run',
  npv_source_run_id: 'baseline-123', spark: []
};

describe('WellCard', () => {
  it('labels per-well NPV as a whole-horizon value, separate from the dated snapshot', () => {
    window.localStorage.setItem('aios-lang', 'en');
    const view = render(<I18nProvider><WellCard payload={payload} /></I18nProvider>);
    expect(screen.getByText('Whole-horizon NPV')).toBeTruthy();
    expect(screen.getByText('producer')).toBeTruthy();
    expect(screen.getByText('available')).toBeTruthy();
    expect(screen.getByText('operating')).toBeTruthy();
    expect(screen.getByText('NPV source: Run data · baseline-123')).toBeTruthy();
    expect(view.container.querySelector('.jarvis-well-context')?.textContent).toContain('2015');

    view.unmount();
    window.localStorage.setItem('aios-lang', 'ru');
    render(<I18nProvider><WellCard payload={payload} /></I18nProvider>);
    expect(screen.getByText('ЧДД за весь горизонт')).toBeTruthy();
    expect(screen.getByText('добывающая')).toBeTruthy();
    expect(screen.getByText('доступна')).toBeTruthy();
    expect(screen.getByText('работает')).toBeTruthy();
    expect(screen.getByText('Источник ЧДД: Расчётные данные · baseline-123')).toBeTruthy();
    expect(screen.getByTestId('well-npv-provenance').getAttribute('title')).toBe('model-z-base-run');
  });
});
