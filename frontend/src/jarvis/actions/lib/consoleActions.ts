import type { Workspace, WorkspaceView } from '@/shared/router/routes';
import { isView, isWorkspace, type ConsoleAction } from '@/jarvis/actions/lib/consoleAction';

export interface ConsoleBridge {
  setRoute: (workspace: Workspace, view: WorkspaceView) => void;
  selectScenario: (id: string) => void;
  selectRun?: (runId: string | null) => void;
  setStepIndex: (index: number) => void;
  selectWell: (well: string | null) => void;
  togglePlay: () => void;
  playing: boolean;
  resolveStepIndex: (controlStep: number) => number | null;
  isWellAvailable: (well: string) => boolean;
  currentScenario: string;
  defaultViewOf: (workspace: Workspace) => WorkspaceView;
  spotlight: (anchor: string) => void;
}

export const APPLY_ORDER = [
  'scenario',
  'run',
  'route',
  'step',
  'well',
  'play',
  'spotlight'
] as const;

export type ApplyStep = (typeof APPLY_ORDER)[number];

export const plannedSteps = (action: ConsoleAction): ApplyStep[] => {
  const steps: ApplyStep[] = [];
  if (action.scenario !== undefined) {
    steps.push('scenario');
  }
  if (action.run_id !== undefined) {
    steps.push('run');
  }
  if (action.workspace !== undefined) {
    steps.push('route');
  }
  if (action.step !== undefined) {
    steps.push('step');
  }
  if (action.well !== undefined) {
    steps.push('well');
  }
  if (action.play !== undefined) {
    steps.push('play');
  }
  if (action.spotlight !== undefined) {
    steps.push('spotlight');
  }
  return steps;
};

export const applyConsoleAction = (
  action: ConsoleAction,
  bridge: ConsoleBridge
): ApplyStep[] => {
  const applied: ApplyStep[] = [];
  const switchingScenario =
    action.scenario !== undefined && action.scenario !== bridge.currentScenario;

  if (switchingScenario && action.scenario !== undefined) {
    bridge.selectScenario(action.scenario);
    applied.push('scenario');
  }

  if (action.run_id !== undefined) {
    if (bridge.selectRun !== undefined) {
      bridge.selectRun(action.run_id);
      applied.push('run');
    }
  }

  if (action.workspace !== undefined && isWorkspace(action.workspace)) {
    const view =
      action.view !== undefined && isView(action.view, action.workspace)
        ? action.view
        : bridge.defaultViewOf(action.workspace);
    bridge.setRoute(action.workspace, view);
    applied.push('route');
  }

  if (action.step !== undefined && !switchingScenario) {
    const step = bridge.resolveStepIndex(action.step);
    if (step !== null) {
      bridge.setStepIndex(step);
      applied.push('step');
    }
  }

  if (
    action.well !== undefined
    && !switchingScenario
    && (action.well === null || bridge.isWellAvailable(action.well))
  ) {
    bridge.selectWell(action.well);
    applied.push('well');
  }

  if (action.play !== undefined && action.play !== bridge.playing) {
    bridge.togglePlay();
    applied.push('play');
  }

  if (action.spotlight !== undefined) {
    bridge.spotlight(action.spotlight);
    applied.push('spotlight');
  }

  return applied;
};
