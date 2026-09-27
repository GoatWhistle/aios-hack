import { useCallback, useEffect, useState } from 'react';
import type { ConstraintsDoc } from '@/entities/scenarios/types';
import type { AlternativeRequest, LiveRun } from '@/pages/money-constraints/model/runTypes';

const POLL_MS = 3000;
const RUNS_URL = '/api/runs';

interface LiveRunsState {
  runs: LiveRun[];
  available: boolean;
  busy: boolean;
  error: string;
  budget: number;
  setBudget: (budget: number) => void;
  start: (
    runId?: string,
    searchConstraints?: ConstraintsDoc,
    caseRequest?: { request_id: string; request: string; scenario: string; base_constraints: ConstraintsDoc }
  ) => Promise<void>;
  startAlternative: (alternativeRequest: AlternativeRequest) => Promise<void>;
  cancel: (runId: string) => Promise<void>;
}

interface LiveRunsOptions {
  document: ConstraintsDoc;
  startFailed: string;
  serverDown: string;
}

export const useLiveRuns = ({
  document,
  startFailed,
  serverDown
}: LiveRunsOptions): LiveRunsState => {
  const [runs, setRuns] = useState<LiveRun[]>([]);
  const [budget, setBudget] = useState(30);
  const [error, setError] = useState('');
  const [sending, setSending] = useState(false);
  const [available, setAvailable] = useState(false);

  useEffect(() => {
    let active = true;
    const load = async (): Promise<void> => {
      try {
        const response = await fetch(RUNS_URL);
        if (!response.ok) {
          throw new Error(serverDown);
        }
        const data = (await response.json()) as { runs?: unknown };
        if (!Array.isArray(data.runs)) {
          throw new Error(serverDown);
        }
        if (active) {
          setRuns(data.runs as LiveRun[]);
          setAvailable(true);
        }
      } catch {
        if (active) {
          setAvailable(false);
        }
      }
    };
    void load();
    const timer = window.setInterval(() => void load(), POLL_MS);
    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, [serverDown]);

  const start = useCallback(
    async (
      runId?: string,
      searchConstraints?: ConstraintsDoc,
      caseRequest?: { request_id: string; request: string; scenario: string; base_constraints: ConstraintsDoc }
    ): Promise<void> => {
      setSending(true);
      setError('');
      try {
        const body =
          runId === undefined
            ? {
                mode: 'search',
                constraints: searchConstraints ?? document,
                budget,
                ...(caseRequest === undefined ? {} : { case_request: caseRequest })
              }
            : { mode: 'verify', run_id: runId };
        const response = await fetch(RUNS_URL, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(body)
        });
        const result = (await response.json()) as LiveRun & { error?: string };
        if (!response.ok) {
          throw new Error(result.error ?? startFailed);
        }
        setRuns((current) => [
          { ...current.find((run) => run.run_id === result.run_id), ...result },
          ...current.filter((run) => run.run_id !== result.run_id)
        ]);
      } catch (failure) {
        setError(failure instanceof Error ? failure.message : serverDown);
      } finally {
        setSending(false);
      }
    },
    [document, budget, startFailed, serverDown]
  );

  const cancel = useCallback(async (runId: string): Promise<void> => {
    setSending(true);
    setError('');
    try {
      const response = await fetch(`${RUNS_URL}/${encodeURIComponent(runId)}`, { method: 'DELETE' });
      const result = (await response.json()) as LiveRun & { error?: string };
      if (!response.ok) throw new Error(result.error ?? startFailed);
      setRuns((current) => current.map((run) => run.run_id === runId ? { ...run, ...result } : run));
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : serverDown);
    } finally {
      setSending(false);
    }
  }, [startFailed, serverDown]);

  const startAlternative = useCallback(async (alternativeRequest: AlternativeRequest): Promise<void> => {
    setSending(true);
    setError('');
    try {
      const response = await fetch(RUNS_URL, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ mode: 'alternative', alternative_request: alternativeRequest })
      });
      const result = (await response.json()) as LiveRun & { error?: string };
      if (!response.ok) throw new Error(result.error ?? startFailed);
      setRuns((current) => [
        { ...current.find((run) => run.run_id === result.run_id), ...result },
        ...current.filter((run) => run.run_id !== result.run_id)
      ]);
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : serverDown);
    } finally {
      setSending(false);
    }
  }, [startFailed, serverDown]);

  return {
    runs,
    available,
    busy: sending || runs.some((run) => run.status === 'running'),
    error,
    budget,
    setBudget,
    start,
    startAlternative,
    cancel
  };
};
