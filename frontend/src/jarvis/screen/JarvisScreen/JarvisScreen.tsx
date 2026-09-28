import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import { useI18n } from '@/shared/i18n/I18nContext';
import type { ConsoleAction } from '@/jarvis/actions/lib/consoleAction';
import { useJarvisSessionContext, useJarvisSphere, useJarvisVoice } from '@/jarvis/provider/contexts';
import { AnswerPanel } from '@/jarvis/scene/AnswerPanel/AnswerPanel';
import { Caption } from '@/jarvis/scene/Caption/Caption';
import { EmptyInvite } from '@/jarvis/screen/JarvisScreen/EmptyInvite';
import { ContextRibbon } from '@/jarvis/scene/ContextRibbon/ContextRibbon';
import { HistoryRail } from '@/jarvis/scene/HistoryRail/HistoryRail';
import { HistorySessions } from '@/jarvis/scene/HistorySessions/HistorySessions';
import { InputDock } from '@/jarvis/scene/InputDock/InputDock';
import { LiveTranscript } from '@/jarvis/voice/LiveTranscript/LiveTranscript';
import { OfflineNotice } from '@/jarvis/scene/OfflineNotice/OfflineNotice';
import { Orbit } from '@/jarvis/scene/Orbit/Orbit';
import { SceneStack } from '@/jarvis/scene/SceneStack/SceneStack';
import { SceneStatus } from '@/jarvis/scene/SceneStatus/SceneStatus';
import { WalkthroughControls } from '@/jarvis/scene/WalkthroughControls/WalkthroughControls';
import { STAGE_SLOT_ID } from '@/jarvis/scene/lib/stageSlot';
import { activeScene } from '@/jarvis/model/scenes';
import { useFocusTrap } from '@/jarvis/provider/useFocusTrap';
import { useSpherePose } from '@/jarvis/stage/SphereFlight/useSpherePose';
import { useVoiceOutput } from '@/jarvis/voice/useVoiceOutput';
import { isEditableTarget } from '@/shared/lib/keyboard/target';
import { useInviteOffset } from '@/jarvis/screen/JarvisScreen/useInviteOffset';
import './JarvisScreen.css';

export const JarvisScreen = () => {
  const { lang, t } = useI18n();
  const {
    scenes,
    sessionId,
    askContext,
    askQuestion,
    cancel,
    selectScene,
    close,
    transition,
    applyAction,
    canRestorePrevious,
    showCompanion,
    capabilities,
    briefingLoading,
    questionDraft,
    setQuestionDraft
  } = useJarvisSessionContext();
  const {
    speakEnabled,
    micOpen,
    voiceAsked,
    clearVoiceAsked
  } = useJarvisVoice();
  const { setAudioLevel } = useJarvisSphere();
  const ref = useRef<HTMLDivElement>(null);
  const bodyRef = useRef<HTMLDivElement>(null);
  const sayRef = useRef<HTMLDivElement>(null);
  const [focusSignal, setFocusSignal] = useState(0);
  const open = transition.phase === 'open';
  const scene = activeScene(scenes);
  const pose = useSpherePose();
  const sceneId = scene?.id ?? null;
  useInviteOffset(ref, sayRef, open && scene === null && pose === 'resting');
  useLayoutEffect(() => {
    if (bodyRef.current !== null) bodyRef.current.scrollTop = 0;
  }, [sceneId]);
  const history = useMemo(
    () => scenes.scenes.map((entry) => entry.question).filter((text) => text.length > 0),
    [scenes.scenes]
  );

  useFocusTrap(ref, open, close);
  const voice = useVoiceOutput({
    enabled: speakEnabled || voiceAsked,
    lang,
    ttsAvailable: capabilities.tts,
    text: scene?.caption ?? null,
    answer: scene?.answer ?? null,
    onLevel: setAudioLevel,
    onSpoken: clearVoiceAsked
  });

  useEffect(() => {
    if (open) {
      setFocusSignal((value) => value + 1);
    }
  }, [open]);

  useEffect(() => {
    if (!open) {
      return;
    }
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.ctrlKey || event.metaKey || event.altKey || isEditableTarget(event.target)) return;
      if (event.key === '/') {
        event.preventDefault();
        setFocusSignal((value) => value + 1);
        return;
      }
    };
    window.addEventListener('keydown', onKeyDown);
    return () => {
      window.removeEventListener('keydown', onKeyDown);
    };
  }, [open, selectScene, scenes.activeIndex]);

  const onOpen = useCallback(
    (action: ConsoleAction) => {
      applyAction(action);
      showCompanion();
      close();
    },
    [applyAction, showCompanion, close]
  );

  return (
    <div
      className="jarvis-screen"
      ref={ref}
      role="dialog"
      aria-modal="true"
      aria-label={t('jarvis-screen.dialogLabel')}
    >
      <ContextRibbon
        speaking={voice.speaking}
        onStop={voice.stop}
        onReadAll={voice.readAll}
        canRestorePrevious={canRestorePrevious}
        onRestorePrevious={() => applyAction({ restore_previous: true })}
      />
      <div className="jarvis-screen-body" ref={bodyRef}>
        <div className="jarvis-screen-identity" data-pose={pose}>
          <span className="jarvis-screen-slot" id={STAGE_SLOT_ID} aria-hidden="true" />
          <SceneStack scenes={scenes.scenes} activeIndex={scenes.activeIndex} />
          {pose === 'perched' ? (
            <button
              type="button"
              className="jarvis-screen-exit"
              aria-label={t('jarvis-stage.closeLabel')}
              aria-keyshortcuts="Escape"
              onClick={close}
            />
          ) : null}
        </div>
        <div className="jarvis-screen-workspace">
        <div className="jarvis-screen-say" ref={sayRef}>
          {scene?.question ? <h2 className="jarvis-screen-question">{scene.question}</h2> : null}
          <OfflineNotice pose={pose} />
          {scene === null ? (
            capabilities.ok ? <EmptyInvite onPick={askQuestion} /> : null
          ) : (
            <Caption scene={scene} />
          )}
          <SceneStatus
            status={scenes.status}
            tool={scenes.tool}
            micOpen={micOpen}
            scene={scene}
          />
          <LiveTranscript />
        </div>
        {scene === null ? null : <Orbit cards={scene.cards} onOpen={onOpen} briefingLoading={scene.question === '' && (scenes.status !== null || briefingLoading)} />}
        <AnswerPanel scene={scene} />
        </div>
      </div>
      <footer className="jarvis-screen-foot">
        <HistoryRail
          scenes={scenes.scenes}
          activeIndex={scenes.activeIndex}
          onSelect={selectScene}
          suggestions={scenes.status === null ? scenes.suggestions : []}
          onPickSuggestion={askQuestion}
        />
        <InputDock
          onAsk={askQuestion}
          focusSignal={focusSignal}
          history={history}
          sessionId={sessionId}
          busy={scenes.status !== null}
          onCancel={cancel}
          draft={questionDraft}
          onDraftChange={setQuestionDraft}
          trail={<HistorySessions />}
          lead={
            <WalkthroughControls
              scenes={scenes}
              context={askContext}
              busy={scenes.status !== null}
              askQuestion={askQuestion}
              selectScene={selectScene}
              applyAction={applyAction}
              cancel={cancel}
            />
          }
        />
      </footer>
    </div>
  );
};
