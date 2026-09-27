import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { I18nProvider } from '@/shared/i18n/I18nContext';
import { JarvisSessionContext } from '@/jarvis/provider/contexts';
import type { JarvisSessionValue } from '@/jarvis/model/jarvisValue';
import type { ScenesState } from '@/jarvis/model/scenes';
import { JarvisCompanion } from '@/jarvis/stage/JarvisCompanion/JarvisCompanion';

const series = {
  run_id: 'run-62-verified',
  well: '19',
  role: 'PROD',
  metric: 'liquid_rate',
  unit: 'm3/day',
  input_source: 'recorded OPM response',
  schedule_source: 'recorded final schedule',
  rows: [
    { step: 9, date: '2007-10-01', input_rate: 63.1, scheduled_rate: 63.0 },
    { step: 10, date: '2007-11-01', input_rate: 60.23, scheduled_rate: 62.6 }
  ]
};

const scenes = {
  scenes: [{
    id: 'scene-1',
    sourceId: 'scene-1',
    question: 'Почему изменилась уставка скважины 19?',
    context: {
      scenario: 'base', step: 10, date: '2007-11-01', selected_well: '19',
      run_id: 'run-62-verified', workspace: 'decisions', view: 'rules', context_version: 'v1'
    },
    cards: [{
      id: 'card-1',
      order: 1,
      tool: 'decision_journal',
      args: { well: '19', step: 10 },
      card: {
        type: 'rule',
        title: 'Записанное решение',
        payload: { run_id: series.run_id, well: '19', step: 10, run_series: series },
        provenance: 'recorded-generation-journal'
      }
    }],
    captionDraft: '',
    caption: 'Записанный отклик и уставка на шаге 10.',
    answerDraft: '',
    answer: null,
    ts: null,
    guarded: true,
    warnings: [],
    error: null,
    done: true
  }],
  activeIndex: 0,
  suggestions: [],
  status: null,
  tool: null,
  seq: 1
} satisfies ScenesState;

describe('JarvisCompanion run-backed decision context', () => {
  it('keeps the recorded series, selected step, question, and answer beside the console', () => {
    const open = vi.fn();
    render(
      <I18nProvider>
        <JarvisSessionContext.Provider value={{
          companionVisible: true,
          scenes,
          open,
          hideCompanion: vi.fn()
        } as unknown as JarvisSessionValue}>
          <JarvisCompanion />
        </JarvisSessionContext.Provider>
      </I18nProvider>
    );

    expect(screen.getByRole('complementary', { name: 'Объяснение Джарвиса рядом с консолью' })).toBeTruthy();
    expect(screen.getByText('Почему изменилась уставка скважины 19?')).toBeTruthy();
    expect(screen.getByText('Записанный отклик и уставка на шаге 10.')).toBeTruthy();
    expect(screen.getByRole('img', { name: 'Временной ряд прогона run-62-verified, скважина 19' })).toBeTruthy();
    expect(screen.getByText(/Шаг 10.*Уставка итогового плана/)).toBeTruthy();
    expect(screen.getByText('октябрь 2007 г.')).toBeTruthy();
    expect(screen.getByText('ноябрь 2007 г.')).toBeTruthy();

    fireEvent.click(screen.getByRole('button', { name: 'Открыть детали и продолжить' }));
    expect(open).toHaveBeenCalledOnce();
  });

  it('does not render a companion when the decision panel is hidden', () => {
    render(
      <I18nProvider>
        <JarvisSessionContext.Provider value={{
          companionVisible: false,
          scenes,
          open: vi.fn(),
          hideCompanion: vi.fn()
        } as unknown as JarvisSessionValue}>
          <JarvisCompanion />
        </JarvisSessionContext.Provider>
      </I18nProvider>
    );

    expect(screen.queryByRole('complementary', { name: 'Объяснение Джарвиса рядом с консолью' })).toBeNull();
  });
});
