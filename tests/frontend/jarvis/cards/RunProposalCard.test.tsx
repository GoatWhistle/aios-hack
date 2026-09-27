import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { I18nProvider } from '@/shared/i18n/I18nContext';
import { RunProposalCard } from '@/jarvis/cards/RunProposalCard/RunProposalCard';

afterEach(() => vi.unstubAllGlobals());

const base = { injection_limits: { '2007': 30000 } };
const caseProposal = {
  request_id: 'jarvis-case-1', request: 'Установи лимит закачки 12000 м3/сут в 2007 году',
  scenario: 'base', operation: 'set_annual_rate_limit', section: 'injection_limits',
  year: 2007, before: 30000, after: 12000, unit: 'm3/day',
  base_constraints: base, constraints: { injection_limits: { '2007': 12000 } },
  requires_confirmation: true
};

it('shows a proposal without launching, then submits the exact reviewed case', async () => {
  const fetch = vi.fn()
    .mockResolvedValueOnce({ status: 404, ok: false })
    .mockResolvedValueOnce({ ok: true, json: async () => ({
      run_id: 'web-new', mode: 'search', status: 'running', message: 'Поиск…',
      budget: 30, progress: { stage: 'search', step: 1, total: 10 }
    }) });
  vi.stubGlobal('fetch', fetch);
  render(<I18nProvider><RunProposalCard type="case-proposal" payload={caseProposal} onOpen={vi.fn()} /></I18nProvider>);

  expect(screen.getByText(/Лимит закачки за 2007: 30000 → 12000 м³\/сут/)).toBeTruthy();
  await waitFor(() => expect(fetch).toHaveBeenCalledTimes(1));
  expect(fetch.mock.calls[0][0]).toBe('/api/runs/by-request/jarvis-case-1');
  fireEvent.click(screen.getByRole('button', { name: 'Подтвердить и запустить' }));
  expect(await screen.findByText('Поиск…')).toBeTruthy();
  expect(screen.queryByText('Это черновик. Расчёт начнётся только после подтверждения.')).toBeNull();
  expect(JSON.parse(fetch.mock.calls[1][1].body)).toEqual({
    mode: 'search', budget: 30,
    constraints: caseProposal.constraints,
    case_request: {
      request_id: caseProposal.request_id, request: caseProposal.request,
      scenario: 'base', base_constraints: base
    }
  });
  expect(screen.getByText('Новый прогон: web-new')).toBeTruthy();
});

it('restores a confirmed alternative run from its request ID after reload', async () => {
  const proposal = {
    request_id: 'jarvis-alternative-1', source_run_id: 'verified-1',
    source_manifest_hash: 'a'.repeat(64), source_economics_hash: 'b'.repeat(64),
    source_schedule_hash: 'c'.repeat(64), alternative_schedule_hash: 'd'.repeat(64),
    constraints_hash: 'e'.repeat(64), source_npv_rub: 1200,
    additional_opm_evaluations: 1, requires_confirmation: true,
    action: { well: '13', from_step: 4, through_step: 6,
      original_target_m3_per_day: 40, alternative_target_m3_per_day: 50 }
  };
  const fetch = vi.fn().mockImplementation(async (url: string) => ({ ok: true, json: async () =>
    url.endsWith('/comparison')
      ? { comparison: { status: 'not-comparable', npv_delta_rub: null, reason: 'missing source methodology hash' } }
      : { run_id: 'web-restored', mode: 'alternative', status: 'completed',
          message: 'Готово', budget: 30, comparison_available: true }
  }));
  vi.stubGlobal('fetch', fetch);
  render(<I18nProvider><RunProposalCard type="alternative-proposal" payload={proposal} onOpen={vi.fn()} /></I18nProvider>);

  expect(await screen.findByText('Новый прогон: web-restored')).toBeTruthy();
  expect(screen.queryByRole('button', { name: 'Подтвердить и запустить' })).toBeNull();
  expect(screen.getByRole('link', { name: 'Открыть сохранённое сравнение' }).getAttribute('href'))
    .toBe('/api/runs/web-restored/comparison');
  expect(await screen.findByText(/изменение ЧДД не публикуется/)).toBeTruthy();
  expect(fetch).toHaveBeenCalledWith('/api/runs/by-request/jarvis-alternative-1');
});

it('does not show the previous job when a different proposal replaces the scene', async () => {
  const fetch = vi.fn().mockImplementation(async (url: string) => url.endsWith('/jarvis-case-1')
    ? { ok: true, json: async () => ({ run_id: 'old-job', status: 'completed', message: 'Old result' }) }
    : { ok: false, status: 404 });
  vi.stubGlobal('fetch', fetch);
  const { rerender } = render(<I18nProvider><RunProposalCard type="case-proposal" payload={caseProposal} onOpen={vi.fn()} /></I18nProvider>);
  expect(await screen.findByText('Новый прогон: old-job')).toBeTruthy();
  rerender(<I18nProvider><RunProposalCard type="case-proposal" payload={{ ...caseProposal, request_id: 'another-case' }} onOpen={vi.fn()} /></I18nProvider>);
  expect(screen.queryByText('Новый прогон: old-job')).toBeNull();
  expect(screen.getByRole('button', { name: 'Подтвердить и запустить' })).toBeTruthy();
  await waitFor(() => expect(fetch).toHaveBeenCalledWith('/api/runs/by-request/another-case'));
});

it('shows recorded rejection reasons and the search budget boundary', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => ({
    run_id: 'rejected-job', status: 'failed', message: 'No feasible candidate',
    evaluations: 20, feasible_evaluations: 0,
    rejection_reasons: ['candidate outside the training domain']
  }) }));
  render(<I18nProvider><RunProposalCard type="case-proposal" payload={caseProposal} onOpen={vi.fn()} /></I18nProvider>);
  expect(await screen.findByText('candidate outside the training domain')).toBeTruthy();
  expect(screen.getByText('Оценено планов: 20. Допустимых на этапе поиска: 0.')).toBeTruthy();
  expect(screen.getByText(/не доказывает отсутствие решения/)).toBeTruthy();
});
