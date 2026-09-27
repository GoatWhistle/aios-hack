import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { ErrorCard } from '@/jarvis/cards/ErrorCard/ErrorCard';
import { I18nProvider } from '@/shared/i18n/I18nContext';
import { dictionaries } from '@/shared/i18n/dictionaries';

describe('ErrorCard', () => {
  it('shows the tool reason and a localized next step instead of a generic error', () => {
    render(
      <I18nProvider>
        <ErrorCard payload={{
          tool: 'find_patterns',
          message: 'the detectors found no anomaly for well W3',
          next_step: 'Check the selected scenario, well and step against available data.',
          expected_card: 'pattern'
        }} />
      </I18nProvider>
    );

    expect(screen.getByText('the detectors found no anomaly for well W3')).toBeTruthy();
    expect(screen.getByText('Check the selected scenario, well and step against available data.')).toBeTruthy();
    expect(screen.getByText('Диагностика')).toBeTruthy();
    expect(screen.queryByText('Что-то пошло не так')).toBeNull();
  });

  it('falls back to localized error text when the service provides no message', () => {
    render(<I18nProvider><ErrorCard payload={{ tool: 'find_patterns' }} /></I18nProvider>);

    expect(screen.getByText('Что-то пошло не так')).toBeTruthy();
  });

  it('has localized labels for all registered Jarvis tool names', () => {
    const tools = [
      'well_snapshot', 'well_series', 'compare_wells', 'field_metrics', 'field_events',
      'rank_wells', 'connectivity', 'find_patterns', 'explain_decision', 'decision_journal',
      'rule_impact', 'compare_scenarios', 'explain_term', 'platform_guide', 'run_status',
      'submission_summary', 'search_docs', 'system_map', 'system_status', 'run_history',
      'run_detail', 'compare_runs', 'case_constraints', 'council_step', 'physics_report'
    ];

    for (const tool of tools) {
      expect(dictionaries.ru[`jarvis-cards.toolName.${tool}`]).toBeTruthy();
      expect(dictionaries.en[`jarvis-cards.toolName.${tool}`]).toBeTruthy();
    }
  });
});
