import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { I18nProvider } from '@/shared/i18n/I18nContext';
import { SeriesCard } from '@/jarvis/cards/SeriesCard';

describe('SeriesCard dates', () => {
  it('shows the recorded interval endpoints in the selected language', () => {
    const payload = {
      metric: 'liquid_rate', unit: 'm3/day',
      rows: [
        { step: 0, date: '2007-01-01', value: 12 },
        { step: 12, date: '2008-01-01', value: 10 }
      ]
    };
    window.localStorage.setItem('aios-lang', 'en');
    const view = render(<I18nProvider><SeriesCard payload={payload} /></I18nProvider>);
    expect(screen.getByText('January 2007')).toBeTruthy();
    expect(screen.getByText('January 2008')).toBeTruthy();

    view.unmount();
    window.localStorage.setItem('aios-lang', 'ru');
    render(<I18nProvider><SeriesCard payload={payload} /></I18nProvider>);
    expect(screen.getByText('январь 2007 г.')).toBeTruthy();
    expect(screen.getByText('январь 2008 г.')).toBeTruthy();
  });

  it('renders a dash when an endpoint date is absent', () => {
    render(<I18nProvider><SeriesCard payload={{
      metric: 'liquid_rate', unit: 'm3/day', rows: [
        { step: 0, date: '', value: 12 }, { step: 1, date: 'not-a-date', value: 10 }
      ]
    }} /></I18nProvider>);
    expect(screen.getAllByText('—')).toHaveLength(2);
  });
});
