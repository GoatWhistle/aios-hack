import { useCallback, useEffect, useRef, useState } from 'react';
import { WORKSPACE_VIEWS, type Workspace, type WorkspaceView } from '@/shared/router/routes';
import { useRoute } from '@/shared/router/RouterProvider';
import { usePlayback } from '@/entities/timeline/model/PlaybackContext';
import { useScenario } from '@/entities/scenarios/model/ScenarioContext';
import { useTimeline } from '@/entities/timeline/model/TimelineContext';
import { applyConsoleAction, type ConsoleBridge } from '@/jarvis/actions/lib/consoleActions';
import type { ConsoleAction } from '@/jarvis/actions/lib/consoleAction';
import { spotlightAnchor } from '@/jarvis/actions/lib/spotlight';

interface Pending {
  scenario: string;
  step?: number;
  well?: string | null;
  settled?: boolean;
}

interface FocusSnapshot {
  scenario: string;
  runId: string | null;
  workspace: Workspace;
  view: WorkspaceView;
  step?: number;
  well: string | null;
}

const ignoreRunSelection = (_runId: string | null): void => undefined;

export const useConsoleActions = (
  selectRun: (runId: string | null) => void = ignoreRunSelection,
  selectedRunId: string | null = null
): { applyAction: (action: ConsoleAction) => void; canRestorePrevious: boolean } => {
  const { setRoute, workspace, view } = useRoute();
  const { activeId, selectScenario } = useScenario();
  const { timeline, stepIndex, setStepIndex, selectedWell, selectWell } = useTimeline();
  const { playing, togglePlay } = usePlayback();
  const [pending, setPendingState] = useState<Pending | null>(null);
  const pendingRef = useRef<Pending | null>(null);
  const setPending = useCallback((next: Pending | null) => {
    pendingRef.current = next;
    setPendingState(next);
  }, []);
  const [canRestorePrevious, setCanRestorePrevious] = useState(false);
  const focusHistory = useRef<FocusSnapshot[]>([]);
  const current = activeId === '' ? 'base' : activeId;

  useEffect(() => {
    const waiting = pending;
    if (waiting === null || waiting !== pendingRef.current || waiting.scenario !== current || timeline.status === 'loading') {
      return;
    }
    if (timeline.status === 'error' || timeline.data.steps.length === 0) {
      setPending(null);
      return;
    }
    const step = waiting.step === undefined
      ? undefined
      : timeline.data.steps.findIndex((item) => item.control_step === waiting.step);
    const wellExists = waiting.well === undefined
      || waiting.well === null
      || timeline.data.wells.includes(waiting.well);
    if ((waiting.step !== undefined && step === -1) || !wellExists) {
      setPending(null);
      return;
    }
    const stepSettled = step === undefined || stepIndex === step;
    const wellSettled = waiting.well === undefined || selectedWell === waiting.well;
    if (stepSettled && wellSettled) {
      if (waiting.settled) {
        setPending(null);
      } else {
        setPending({ ...waiting, settled: true });
      }
      return;
    }
    if (step !== undefined && step >= 0) {
      setStepIndex(step);
    }
    if (waiting.well !== undefined) {
      selectWell(waiting.well);
    }
  }, [pending, current, timeline, stepIndex, selectedWell, setStepIndex, selectWell, setPending]);

  const applyAction = useCallback(
    (action: ConsoleAction) => {
      // An earlier effect must not settle or replay a superseded navigation.
      setPending(null);
      if (action.restore_previous) {
        const previous = focusHistory.current.pop();
        setCanRestorePrevious(focusHistory.current.length > 0);
        if (previous === undefined) return;
        const switchingScenario = previous.scenario !== current;
        if (switchingScenario || timeline.status !== 'ready') {
          setPending({
            scenario: previous.scenario,
            step: previous.step,
            well: previous.well
          });
        }
        const restoreBridge: ConsoleBridge = {
          setRoute,
          selectScenario,
          selectRun,
          setStepIndex: (index: number) => setStepIndex(index),
          selectWell,
          togglePlay,
          playing,
          resolveStepIndex: (controlStep: number) => {
            if (!Number.isInteger(controlStep) || timeline.status !== 'ready') return null;
            const index = timeline.data.steps.findIndex((item) => item.control_step === controlStep);
            return index < 0 ? null : index;
          },
          isWellAvailable: (well: string) =>
            timeline.status === 'ready' && timeline.data.wells.includes(well),
          currentScenario: current,
          defaultViewOf: (target: Workspace): WorkspaceView => WORKSPACE_VIEWS[target][0],
          spotlight: () => undefined
        };
        applyConsoleAction({
          scenario: previous.scenario,
          run_id: previous.runId,
          workspace: previous.workspace,
          view: previous.view,
          step: previous.step,
          well: previous.well,
          play: false
        }, restoreBridge);
        return;
      }
      const switchingScenario = action.scenario !== undefined && action.scenario !== current;
      const waitingForTimeline = timeline.status !== 'ready';
      if (
        switchingScenario
        || (waitingForTimeline && (action.step !== undefined || action.well !== undefined))
      ) {
        setPending({
          scenario: action.scenario ?? current,
          step: action.step,
          well: action.well
        });
      }
      const bridge: ConsoleBridge = {
        setRoute,
        selectScenario,
        selectRun,
        setStepIndex: (index: number) => setStepIndex(index),
        selectWell,
        togglePlay,
        playing,
        resolveStepIndex: (controlStep: number) => {
          if (!Number.isInteger(controlStep) || timeline.status !== 'ready') return null;
          const index = timeline.data.steps.findIndex((item) => item.control_step === controlStep);
          return index < 0 ? null : index;
        },
        isWellAvailable: (well: string) =>
          timeline.status === 'ready' && timeline.data.wells.includes(well),
        currentScenario: current,
        defaultViewOf: (workspace: Workspace): WorkspaceView => WORKSPACE_VIEWS[workspace][0],
        spotlight: (anchor: string) => {
          requestAnimationFrame(() => {
            requestAnimationFrame(() => {
              spotlightAnchor(anchor);
            });
          });
        }
      };
      const before: FocusSnapshot = {
        scenario: current,
        runId: selectedRunId,
        workspace,
        view,
        step: timeline.status === 'ready'
          ? timeline.data.steps[stepIndex]?.control_step
          : undefined,
        well: selectedWell
      };
      const applied = applyConsoleAction(action, bridge);
      if (applied.some((step) => ['scenario', 'run', 'route', 'step', 'well'].includes(step))) {
        focusHistory.current.push(before);
        setCanRestorePrevious(true);
      }
    },
    [setRoute, workspace, view, selectScenario, selectRun, selectedRunId, setStepIndex, selectWell, togglePlay, playing, timeline, current, stepIndex, selectedWell, setPending]
  );

  return { applyAction, canRestorePrevious };
};
