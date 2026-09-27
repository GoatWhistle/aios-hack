import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { I18nProvider } from '@/shared/i18n/I18nContext';
import { EventStripCard } from '@/jarvis/cards/EventStripCard/EventStripCard';

describe('EventStripCard', () => {
  it('exposes the exact event date, step, well and localized type in its details', () => {
    render(
      <I18nProvider>
        <EventStripCard payload={{
          from_step: 0,
          to_step: 12,
          events: [{ step: 12, date: '2008-01-01', well: 'W2', type: 'ROLE_CHANGE' }]
        }} />
      </I18nProvider>
    );

    expect(screen.getByText('Даты, скважины и шаги событий')).toBeTruthy();
    expect(screen.getByText(/1 янв\. 2008 г\..*шаг 12.*Скважина W2.*Перевод/)).toBeTruthy();
  });

  it('explains an empty successful result and recommends widening the range', () => {
    render(
      <I18nProvider>
        <EventStripCard payload={{
          from_step: 10, to_step: 20,
          from_date: '2007-11-01', to_date: '2008-09-01', events: []
        }} />
      </I18nProvider>
    );

    expect(screen.getByText(/Событий не найдено с 1 нояб\. 2007 г\. по 1 сент\. 2008 г\./)).toBeTruthy();
    expect(screen.queryByRole('list')).toBeNull();
  });
});
