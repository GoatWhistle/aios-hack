import { act, render, screen, waitFor } from '@testing-library/react';
import { useState } from 'react';
import type { ReactNode } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { TimelineFile, TimelineWellRow } from '@/entities/timeline/types';
import { clearJsonCache } from '@/shared/api/jsonCache';
import { I18nProvider } from '@/shared/i18n/I18nContext';
import { RouterProvider, useRoute } from '@/shared/router/RouterProvider';
import { PlaybackProvider } from '@/entities/timeline/model/PlaybackContext';
import { ScenarioProvider, useScenario } from '@/entities/scenarios/model/ScenarioContext';
import { TimelineProvider, useTimeline } from '@/entities/timeline/model/TimelineContext';
import type { ConsoleAction } from '@/jarvis/actions/lib/consoleAction';
import { useConsoleActions } from '@/jarvis/actions/lib/useConsoleActions';

const row = (well: string): TimelineWellRow => ({
  well,
  availability: 'AVAILABLE',
  role: 'PROD',
  operating_status: 'OPEN',
  setpoint: 50,
  liquid_rate: 70,
  injection_rate: 0,
  bhp: 91,
  watercut: 0.5,
  fact_to_target: 1.4,
  cumulative_liquid: 2100
});

const timelineFor = (wells: string[], steps: number, controlSteps?: number[]): TimelineFile => ({
  meta: { kind: 'test', provenance: 'fixture' },
  model: 'Model_Z',
  t0: '2007-01-01',
  n_control_dates: steps,
  n_intervals: steps - 1,
  wells,
  steps: Array.from({ length: steps }, (_, k) => ({
    control_step: controlSteps?.[k] ?? k,
    date: `2007-0${k + 1}-01`,
    terminal: k === steps - 1,
    field: {
      production: 2000 + k,
      injection: 1500 + k,
      compensation: 0.75,
      npv_cumulative: 1000 * (k + 1),
      active_wells: wells.length
    },
    wells: wells.map(row)
  }))
});

const baseTimeline = timelineFor(['10', '11', '12'], 6);
const whatIfTimeline = timelineFor(['10', '11', '12'], 6);

const mockFetch = (base: TimelineFile = baseTimeline) => {
  vi.stubGlobal(
    'fetch',
    vi.fn((url: string) =>
      Promise.resolve({
        ok: true,
        json: () =>
          Promise.resolve(
            url.includes('timeline.json')
              ? url.includes('/whatif/')
                ? whatIfTimeline
                : base
              : {}
          )
      })
    )
  );
};

let run: (action: ConsoleAction) => void;

const Probe = () => {
  const [runId, setRunId] = useState<string | null>(null);
  const { applyAction: apply } = useConsoleActions(setRunId, runId);
  const { workspace, view } = useRoute();
  const { stepIndex, selectedWell, timeline } = useTimeline();
  const { activeId } = useScenario();
  run = apply;

  return (
    <output>
      <span data-testid="scenario">{activeId === '' ? 'base' : activeId}</span>
      <span data-testid="route">{`${workspace}/${view}`}</span>
      <span data-testid="step">{stepIndex}</span>
      <span data-testid="well">{selectedWell ?? 'none'}</span>
      <span data-testid="run">{runId ?? 'none'}</span>
      <span data-testid="timeline-status">{timeline.status}</span>
    </output>
  );
};

const harness = (): ReactNode => (
  <I18nProvider>
    <RouterProvider>
      <ScenarioProvider>
        <TimelineProvider>
          <PlaybackProvider>
            <Probe />
          </PlaybackProvider>
        </TimelineProvider>
      </ScenarioProvider>
    </RouterProvider>
  </I18nProvider>
);

const value = (id: string): string => screen.getByTestId(id).textContent ?? '';

describe('applying a card action to the console', () => {
  beforeEach(() => {
    clearJsonCache();
    mockFetch();
  });
  afterEach(() => vi.unstubAllGlobals());

  it('carries route, step and well when the scenario stays the same', async () => {
    render(harness());
    await waitFor(() => expect(value('timeline-status')).toBe('ready'));

    act(() => {
      run({ workspace: 'field', view: 'projection', step: 3, well: '11' });
    });

    await waitFor(() => {
      expect(value('route')).toBe('field/projection');
      expect(value('step')).toBe('3');
      expect(value('well')).toBe('11');
    });
  });

  it('keeps the explanation run selected when opening its separately sourced measured map', async () => {
    mockFetch(timelineFor(['19'], 2, [10, 11]));
    render(harness());
    await waitFor(() => expect(value('timeline-status')).toBe('ready'));

    act(() => {
      run({
        scenario: 'base',
        run_id: 'jarvis-policy-20260926',
        workspace: 'field',
        view: 'projection',
        step: 10,
        well: '19'
      });
    });

    await waitFor(() => {
      expect(value('scenario')).toBe('base');
      expect(value('route')).toBe('field/projection');
      expect(value('step')).toBe('0');
      expect(value('well')).toBe('19');
      expect(value('run')).toBe('jarvis-policy-20260926');
    });
  });

  it('queues a valid focus action while the timeline is loading', async () => {
    render(harness());

    act(() => run({ step: 3, well: '11' }));

    await waitFor(() => {
      expect(value('timeline-status')).toBe('ready');
      expect(value('step')).toBe('3');
      expect(value('well')).toBe('11');
    });
  });

  it('keeps step and well after a scenario switch resets the timeline', async () => {
    render(harness());
    await waitFor(() => expect(value('timeline-status')).toBe('ready'));

    act(() => {
      run({
        scenario: 'whatif',
        workspace: 'field',
        view: 'projection',
        step: 4,
        well: '12'
      });
    });

    await waitFor(() => expect(value('scenario')).toBe('whatif'));
    await waitFor(() => {
      expect(value('route')).toBe('field/projection');
      expect(value('step')).toBe('4');
      expect(value('well')).toBe('12');
    });
  });

  it('leaves the console alone when the action names nothing', async () => {
    render(harness());
    await waitFor(() => expect(value('timeline-status')).toBe('ready'));

    act(() => {
      run({});
    });

    await waitFor(() => {
      expect(value('route')).toBe('overview/fund');
      expect(value('step')).toBe('0');
      expect(value('well')).toBe('none');
    });
  });

  it('rejects a missing step rather than clamping to the timeline edge', async () => {
    render(harness());
    await waitFor(() => expect(value('timeline-status')).toBe('ready'));

    act(() => run({ step: 99 }));

    expect(value('step')).toBe('0');
  });

  it('does not select a well absent from the active scenario', async () => {
    render(harness());
    await waitFor(() => expect(value('timeline-status')).toBe('ready'));

    act(() => run({ step: 3, well: '999' }));

    expect(value('step')).toBe('3');
    expect(value('well')).toBe('none');
  });

  it('resolves a control step to its actual timeline index', async () => {
    mockFetch(timelineFor(['10', '11'], 2, [10, 20]));
    render(harness());
    await waitFor(() => expect(value('timeline-status')).toBe('ready'));

    act(() => run({ step: 20 }));

    expect(value('step')).toBe('1');
  });

  it('restores the previous route, scenario, run, well and control step', async () => {
    render(harness());
    await waitFor(() => expect(value('timeline-status')).toBe('ready'));

    act(() => run({
      scenario: 'whatif',
      run_id: 'run-a',
      workspace: 'field',
      view: 'maps',
      step: 3,
      well: '11'
    }));
    await waitFor(() => {
      expect(value('scenario')).toBe('whatif');
      expect(value('route')).toBe('field/maps');
      expect(value('step')).toBe('3');
      expect(value('well')).toBe('11');
      expect(value('run')).toBe('run-a');
    });

    act(() => run({
      scenario: 'base',
      run_id: 'run-b',
      workspace: 'money',
      view: 'rank',
      step: 1,
      well: '12'
    }));
    await waitFor(() => {
      expect(value('scenario')).toBe('base');
      expect(value('route')).toBe('money/rank');
      expect(value('run')).toBe('run-b');
    });

    act(() => run({ restore_previous: true }));
    await waitFor(() => {
      expect(value('scenario')).toBe('whatif');
      expect(value('route')).toBe('field/maps');
      expect(value('step')).toBe('3');
      expect(value('well')).toBe('11');
      expect(value('run')).toBe('run-a');
    });
  });
});
