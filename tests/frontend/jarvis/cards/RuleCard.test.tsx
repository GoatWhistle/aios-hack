import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { I18nProvider } from '@/shared/i18n/I18nContext';
import { formatCalendarDate } from '@/shared/lib/format';
import { RuleCard } from '@/jarvis/cards/RuleCard/RuleCard';

describe('RuleCard feedback response comparison', () => {
  it('localizes recorded input names and checks units by the field suffix', () => {
    const { container } = render(
      <I18nProvider>
        <RuleCard payload={{
          run_id: 'run-input-units', well: '62', step: 0,
          rule_facts: [{ level: 'GROUP', agent: 'FieldCoordinator', entry: {
            rule: 'R1', decision: 'SET_RATE', inputs: {
              water_ceiling_m3_per_day: 42,
              gross_value_rub_per_m3: 6004.867,
              oil_density_t_per_m3: 0.9131,
              producers_covered: 57,
              binding_source: 1,
              theta_r2_gain: 0.25,
              theta_r3_reopen_margin: 0.1
            }
          } }]
        }} onOpen={vi.fn()} />
      </I18nProvider>
    );

    expect(container.textContent).toContain('Лимит закачки воды');
    expect(container.textContent).toContain('Валовая ценность кубометра');
    expect(container.textContent).toContain('Плотность нефти');
    expect(container.textContent).toContain('Охвачено добывающих скважин');
    expect(container.textContent).toContain('42 м³/сут');
    expect(container.textContent).toContain('6 004,867 руб./м³');
    expect(container.textContent).toContain('0,9131 т/м³');
    expect(container.textContent).toContain('57 скважин');
    expect(container.textContent).toContain('1 единица не указана');
    expect(container.textContent).toContain('Группа · Координатор поля');
    expect(container.textContent).toContain('Ценность закачки (R1)');
    expect(container.textContent).toContain('0,25 коэффициент');
    expect(container.textContent).toContain('0,1 доля');
  });

  it('formats decision evidence values from known metric keys and event kinds', () => {
    const { container } = render(
      <I18nProvider>
        <RuleCard
          payload={{
            run_id: 'run-evidence', well: '19', step: 12,
            input_observation: { liquid_rate: 12.5, watercut: 0.6, bhp: 230, npv_rub: 1500 },
            plan_check: { opm_status: 'OK', sound: true },
            rule_facts: [{ level: 'WELL', agent: '19', entry: {
              rule: 'R1', decision: 'SET_LRAT 10', inputs: { injection_rate: 8 }
            } }],
            final_schedule_events: [{ kind: 'SET_LRAT', well: '19', value: 10 }]
          }}
          onOpen={vi.fn()}
        />
      </I18nProvider>
    );

    expect(container.textContent).toMatch(/12,5\sм³\/сут/);
    expect(container.textContent).toMatch(/60\s?%/);
    expect(container.textContent).toMatch(/230\sбар/);
    expect(container.textContent).toMatch(/1\s?500\sруб\./);
    expect(container.textContent).toMatch(/10\sм³\/сут/);
    expect(container.textContent).toContain('Задать дебит жидкости');
    expect(container.textContent).toContain('Скважина 19');
    expect(container.textContent).toContain('расчёт завершён');
    expect(container.textContent).toContain('ограничения пройдены: да');
    expect(container.textContent).toContain('Задать дебит жидкости 10 м³/сут');
    expect(container.textContent).not.toContain('SET_LRAT 10');
  });

  it('shows pointwise OPM feedback values and the non-causal caveat', () => {
    render(
      <I18nProvider>
        <RuleCard
          payload={{
            run_id: 'run-new',
            well: '19',
            step: 12,
            rule_facts: [],
            feedback_comparison: {
              status: 'pointwise-state-comparison',
              feedback_source_run_id: 'run-feedback',
              date: '2010-01-01',
              interpretation: 'descriptive only',
              metrics: {
                oil_rate_m3_per_day: {
                  feedback: 10,
                  evaluation: 8,
                  delta_evaluation_minus_feedback: -2
                }
              }
            },
            evaluation_sources: {
              surrogate_prediction: { npv: 15 },
              economic_evaluation: { measured_npv_rub: 12 }
            }
          }}
          onOpen={vi.fn()}
        />
      </I18nProvider>
    );

    expect(screen.getByText('Состояние обратной связи и OPM на ту же дату')).toBeTruthy();
    expect(screen.getByText(/Источник обратной связи: run-feedback/).textContent).toContain(formatCalendarDate('ru', '2010-01-01'));
    expect(screen.getByText(/Дебит нефти/).textContent).toContain(
      '10 м³/сут → 8 м³/сут (разница: -2 м³/сут)'
    );
    expect(screen.getByText(/Оценка суррогата/).textContent).toContain('15 руб.');
    expect(screen.getByText(/Экономическая оценка/).textContent).toContain('12 руб.');
    expect(screen.getByText(/не доказывает причинный эффект/)).toBeTruthy();
  });

  it('opens and focuses the recorded decision journal', () => {
    const { container } = render(
      <I18nProvider>
        <RuleCard
          payload={{ run_id: 'run-recorded', well: '19', step: 12, rule_facts: [] }}
          onOpen={vi.fn()}
        />
      </I18nProvider>
    );
    const details = container.querySelector('details');
    expect(details?.open).toBe(false);

    fireEvent.click(screen.getByRole('button', { name: 'Открыть журнал' }));

    expect(details?.open).toBe(true);
    expect(document.activeElement?.tagName).toBe('SUMMARY');
  });

  it('focuses the run-backed graph from the card action', () => {
    render(
      <I18nProvider>
        <RuleCard
          payload={{
            run_id: 'run-recorded', well: '19', step: 12, rule_facts: [],
            run_series: {
              run_id: 'run-recorded', well: '19', rows: [
                { step: 12, date: '2010-01-01', input_rate: 15, scheduled_rate: 12 }
              ]
            }
          }}
          onOpen={vi.fn()}
        />
      </I18nProvider>
    );

    fireEvent.click(screen.getByRole('button', { name: 'На график' }));

    expect((document.activeElement as HTMLElement).querySelector('svg[role="img"]')).toBeTruthy();
  });

  it('opens measured showcase connections in the network projection, not the geological map', () => {
    const onOpen = vi.fn();
    render(
      <I18nProvider>
        <RuleCard
          payload={{
            run_id: 'run-recorded', well: '19', step: 12, rule_facts: [],
            connectivity_source: { scenario: 'base' },
            run_series: {
              run_id: 'run-recorded', well: '19', rows: [
                { step: 12, date: '2010-01-01', input_rate: 15, scheduled_rate: 12 }
              ]
            }
          }}
          action={{ scenario: 'base', connections_available: true }}
          onOpen={onOpen}
        />
      </I18nProvider>
    );

    fireEvent.click(screen.getByRole('button', { name: 'Показать измеренные связи скважины' }));

    expect(onOpen).toHaveBeenCalledWith({
      scenario: 'base', run_id: 'run-recorded', workspace: 'field', view: 'projection', well: '19', step: 12
    });
  });

  it('localizes a recorded rule statement for the active UI language', () => {
    const { container } = render(
      <I18nProvider>
        <RuleCard payload={{
          rule: 'R1', name: 'Value of injection',
          statement: 'Water flows to the wells where it turns into oil rather than into water.',
          inputs: {}, decision: 'SET_LRAT'
        }} onOpen={vi.fn()} />
      </I18nProvider>
    );

    expect(container.textContent).toContain('Направлять воду в скважины, где она превращается в нефть, а не в воду.');
    expect(container.textContent).not.toContain('Water flows to the wells');
  });

  it('preserves an unknown OPM status code in a recorded plan check', () => {
    const { container } = render(<I18nProvider><RuleCard payload={{
      run_id: 'run-unknown-status', well: '19', step: 12, rule_facts: [],
      plan_check: { opm_status: 'EXTERNAL_STATUS', sound: false }
    }} onOpen={vi.fn()} /></I18nProvider>);
    expect(container.textContent).toContain('EXTERNAL_STATUS');
  });
});
