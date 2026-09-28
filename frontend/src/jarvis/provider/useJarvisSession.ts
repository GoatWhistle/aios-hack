import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  adoptScene,
  emptyScenes,
  scenesReducer,
  selectSceneAt,
  settleRestoredScenes,
  type ScenesState
} from '@/jarvis/model/scenes';
import {
  fetchSessionEvents,
  rememberSessionId,
  replayEvents,
  newSessionId,
  storedSessionId
} from '@/jarvis/model/sessions';
import { QUESTION_LIMIT, type JarvisTransport } from '@/jarvis/transport/JarvisTransport';
import type { JarvisAskContext, JarvisEvent } from '@/jarvis/transport/events';

export interface JarvisSession {
  scenes: ScenesState;
  sessionId: string;
  questionDraft: string;
  setQuestionDraft: (text: string) => void;
  askQuestion: (question: string, context?: JarvisAskContext) => void;
  pushEvents: (events: readonly JarvisEvent[]) => void;
  mergeEvents: (events: readonly JarvisEvent[]) => void;
  loadSession: (id: string) => void;
  startSession: () => void;
  cancel: () => void;
  selectScene: (index: number) => void;
  busy: boolean;
}

export const useJarvisSession = (
  transport: JarvisTransport,
  lang: string,
  askContext: JarvisAskContext
): JarvisSession => {
  const [scenes, setScenes] = useState<ScenesState>(emptyScenes);
  const [busy, setBusy] = useState(false);
  const abortRef = useRef<AbortController | null>(null);
  const pendingSceneRef = useRef<string | null>(null);
  const sessionGeneration = useRef(0);
  const contextVersion = askContext.context_version ?? JSON.stringify(askContext);
  const previousContextVersion = useRef(contextVersion);
  const [sessionId, setSessionId] = useState(() => storedSessionId());
  const [questionDrafts, setQuestionDrafts] = useState<Record<string, string>>({});
  const questionDraft = questionDrafts[sessionId] ?? '';
  const setQuestionDraft = useCallback((text: string) => {
    setQuestionDrafts((drafts) => ({ ...drafts, [sessionId]: text.slice(0, QUESTION_LIMIT) }));
  }, [sessionId]);
  const current = useRef(sessionId);
  current.current = sessionId;

  const settleCancelledScene = useCallback((sourceId: string | null) => {
    setScenes((state) => {
      const index = sourceId === null
        ? state.activeIndex
        : state.scenes.findIndex((scene) => scene.sourceId === sourceId || scene.id === sourceId);
      const scene = state.scenes[index];
      if (index < 0 || scene === undefined || scene.done) {
        return { ...state, status: null, tool: null };
      }
      const scenes = state.scenes.slice();
      scenes[index] = {
        ...scene,
        done: true,
        error: { code: 'cancelled', message: 'request cancelled' }
      };
      return { ...state, scenes, status: null, tool: null };
    });
  }, []);

  const cancel = useCallback(() => {
    if (abortRef.current === null) return;
    abortRef.current.abort();
    abortRef.current = null;
    setBusy(false);
    settleCancelledScene(pendingSceneRef.current);
    pendingSceneRef.current = null;
  }, [settleCancelledScene]);

  useEffect(() => {
    if (previousContextVersion.current === contextVersion) {
      return;
    }
    previousContextVersion.current = contextVersion;
    cancel();
  }, [cancel, contextVersion]);

  const selectScene = useCallback(
    (index: number) => setScenes((state) => selectSceneAt(state, index)),
    []
  );

  const pushEvents = useCallback((events: readonly JarvisEvent[]) => {
    const pendingScene = pendingSceneRef.current;
    abortRef.current?.abort();
    abortRef.current = null;
    setBusy(false);
    pendingSceneRef.current = null;
    if (pendingScene !== null) settleCancelledScene(pendingScene);
    setScenes((state) => settleRestoredScenes(events.reduce((next, event) => scenesReducer(next, event), state)));
  }, [settleCancelledScene]);

  const mergeEvents = useCallback((events: readonly JarvisEvent[]) => {
    const liveSceneId = abortRef.current === null ? null : pendingSceneRef.current;
    setScenes((state) => {
      const merged = events
        .filter((event) => event.type !== 'status' && event.type !== 'error' && event.type !== 'suggestions')
        .reduce((next, event) => scenesReducer(next, event), state);
      return {
        ...settleRestoredScenes(merged, liveSceneId),
        activeIndex: state.scenes.length > 0 ? state.activeIndex : merged.activeIndex,
        status: liveSceneId === null ? null : state.status,
        tool: liveSceneId === null ? null : state.tool,
        suggestions: state.suggestions
      };
    });
  }, []);

  const loadSession = useCallback(
    (id: string) => {
      const generation = sessionGeneration.current + 1;
      sessionGeneration.current = generation;
      if (abortRef.current !== null) {
        abortRef.current.abort();
        abortRef.current = null;
        settleCancelledScene(pendingSceneRef.current);
        pendingSceneRef.current = null;
      }
      abortRef.current = null;
      setBusy(false);
      current.current = id;
      setSessionId(id);
      rememberSessionId(id);
      void fetchSessionEvents(id).then((events) => {
        if (current.current !== id || sessionGeneration.current !== generation) {
          return;
        }
        setScenes(replayEvents(events));
      });
    },
    [settleCancelledScene]
  );

  const startSession = useCallback(() => {
    sessionGeneration.current += 1;
    abortRef.current?.abort();
    abortRef.current = null;
    pendingSceneRef.current = null;
    setBusy(false);
    const next = newSessionId();
    current.current = next;
    setSessionId(next);
    rememberSessionId(next);
    setScenes(emptyScenes);
  }, []);

  const askQuestion = useCallback(
    (question: string, contextOverride?: JarvisAskContext) => {
      const text = question.trim().slice(0, QUESTION_LIMIT);
      if (text.length === 0) {
        return;
      }
      if (abortRef.current !== null) {
        abortRef.current.abort();
        abortRef.current = null;
        settleCancelledScene(pendingSceneRef.current);
        pendingSceneRef.current = null;
      }
      const controller = new AbortController();
      abortRef.current = controller;
      setBusy(true);
      const requestContext = contextOverride ?? askContext;
      const generation = sessionGeneration.current;
      const requestSessionId = current.current;
      const pending = `pending-${Date.now()}`;
      pendingSceneRef.current = pending;
      setScenes((state) =>
        scenesReducer(state, {
          type: 'scene',
          scene_id: pending,
          question: text,
          context: requestContext
        })
      );
      const run = async () => {
        let requestSceneId = pending;
        try {
          for await (const event of transport.ask(
            { sessionId: requestSessionId, question: text, lang, context: requestContext },
            controller.signal
          )) {
            if (event.type === 'scene') {
              if (!controller.signal.aborted && sessionGeneration.current === generation) {
                requestSceneId = event.scene_id;
                pendingSceneRef.current = event.scene_id;
              }
              setScenes((state) => controller.signal.aborted || sessionGeneration.current !== generation
                ? state
                : adoptScene(state, pending, event));
              continue;
            }
            const requestEvent: JarvisEvent = event.type === 'error' && event.scene_id === undefined
              ? { ...event, scene_id: requestSceneId }
              : event;
            setScenes((state) => controller.signal.aborted || sessionGeneration.current !== generation
              ? state
              : scenesReducer(state, requestEvent));
          }
        } catch {
          if (!controller.signal.aborted) {
            setScenes((state) => controller.signal.aborted || sessionGeneration.current !== generation
              ? state
              : scenesReducer(state, {
                type: 'error',
                scene_id: requestSceneId,
                code: 'upstream',
                message: 'transport threw'
              }));
          }
        } finally {
          if (abortRef.current === controller) {
            abortRef.current = null;
            pendingSceneRef.current = null;
            setBusy(false);
          }
        }
      };
      void run();
    },
    [transport, askContext, lang, settleCancelledScene]
  );

  return useMemo(
    () => ({
      scenes,
      sessionId,
      questionDraft,
      setQuestionDraft,
      askQuestion,
      pushEvents,
      mergeEvents,
      loadSession,
      startSession,
      cancel,
      selectScene,
      busy
    }),
    [
      scenes,
      sessionId,
      questionDraft,
      setQuestionDraft,
      askQuestion,
      pushEvents,
      mergeEvents,
      loadSession,
      startSession,
      cancel,
      selectScene,
      busy
    ]
  );
};
