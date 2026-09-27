import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { I18nProvider } from '@/shared/i18n/I18nContext';
import { SubmissionCard } from '@/jarvis/cards/SubmissionCard/SubmissionCard';

describe('SubmissionCard', () => {
  it('localizes known missing package fields and preserves unknown field identifiers', () => {
    const { container } = render(<I18nProvider><SubmissionCard payload={{
      run_id: 'run-incomplete', assembled: true, status: 'ready_to_submit', claimed_npv_rub: 42,
      reason: null, source: 'claimed_npv.json', schedule_include_present: false,
      checks: {
        status_ready_to_submit: false, schedule_include_present: false, source_run_matches: false,
        schedule_hash_matches: false, missing_fields: ['canonical_schedule_hash', 'custom_field']
      }
    }} /></I18nProvider>);

    expect(screen.getByText('Хеш расписания')).toBeTruthy();
    const unknown = container.querySelector('[title="custom_field"]');
    expect(unknown?.textContent).toContain('custom_field');
    expect(unknown?.getAttribute('title')).toBe('custom_field');
  });

  it('distinguishes a missing package from a checked assembled package', () => {
    const { rerender } = render(<I18nProvider><SubmissionCard payload={{
      run_id: 'run-a', assembled: false, status: 'rejected', claimed_npv_rub: null,
      code: 'no-submission', reason: 'package missing at /out/run-a/submission/claimed_npv.json', source: null, schedule_include_present: false, checks: null
    }} /></I18nProvider>);
    expect(screen.getByText('Пакет не собран')).toBeTruthy();
    expect(screen.getByText('Пакет сдачи не собран: заявленный ЧДД не записан.').getAttribute('title')).toBe('package missing at /out/run-a/submission/claimed_npv.json');
    expect(screen.getByText('run-a · отклонён')).toBeTruthy();
    rerender(<I18nProvider><SubmissionCard payload={{
      run_id: 'run-a', assembled: true, status: 'ready_to_submit', claimed_npv_rub: 42,
      code: null, reason: null, source: 'claimed_npv.json', schedule_include_present: true,
      checks: { status_ready_to_submit: true, schedule_include_present: true, source_run_matches: true, schedule_hash_matches: true, missing_fields: [] }
    }} /></I18nProvider>);
    expect(screen.getByText('Пакет собран')).toBeTruthy();
    expect(screen.getByText('run-a · готов к сдаче')).toBeTruthy();
    expect(screen.getByText(/Заявленный ЧДД: 42 руб\./)).toBeTruthy();
    expect(screen.getByText(/Хеш расписания совпадает: да/)).toBeTruthy();
  });
});
