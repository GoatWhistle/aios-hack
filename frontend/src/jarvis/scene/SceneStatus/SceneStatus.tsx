import { useI18n } from '@/shared/i18n/I18nContext';
import { translateOr } from '@/jarvis/i18nFallback';
import { useOptionalJarvisSession } from '@/jarvis/provider/contexts';
import { beadTime } from '@/jarvis/scene/lib/cardGlyphs';
import type { Scene } from '@/jarvis/model/scenes';
import type { JarvisStatusState } from '@/jarvis/transport/events';
import './SceneStatus.css';

interface SceneStatusProps {
  status: JarvisStatusState | null;
  tool: string | null;
  micOpen: boolean;
  scene: Scene | null;
}

export const SceneStatus = ({ status, tool, micOpen, scene }: SceneStatusProps) => {
  const { lang, t } = useI18n();
  const jarvis = useOptionalJarvisSession();
  const failure = scene?.error ?? null;

  if (failure !== null) {
    const reason = translateOr(
      t,
      `jarvis-screen.error.${failure.code}`,
      'jarvis-screen.error.unknown'
    );
    const at = beadTime(lang, scene?.ts ?? null);
    const past = scene?.done === true && status === null;
    const healthy = jarvis?.capabilities.ok === true;

    if (past) {
      const stopped = failure.code === 'cancelled' || failure.code === 'interrupted';
      const cause = translateOr(
        t,
        `jarvis-screen.cause.${failure.code}`,
        'jarvis-screen.cause.unknown'
      );
      const line = stopped
        ? at.length > 0
          ? t('jarvis-screen.pastStoppedAt', { time: at })
          : t('jarvis-screen.pastStopped')
        : at.length > 0
          ? t('jarvis-screen.pastFailureAt', { time: at, cause })
          : t('jarvis-screen.pastFailure', { cause });
      return (
        <p
          className="jarvis-status"
          role="status"
          data-kind="past-error"
          data-tone={stopped ? 'stopped' : undefined}
          data-live={healthy ? undefined : 'down'}
        >
          <span className="jarvis-status-past">{line}</span>
          {jarvis === null || !(healthy || stopped) ? null : (
            <button type="button" className="jarvis-status-retry" data-ready="true" onClick={jarvis.retry}>
              {t('jarvis-screen.askAgain')}
            </button>
          )}
        </p>
      );
    }

    return (
      <p className="jarvis-status" role="alert" data-kind="error">
        {reason}
        {jarvis === null ? null : (
          <button type="button" className="jarvis-status-retry" onClick={jarvis.retry}>
            {t('jarvis-screen.retry')}
          </button>
        )}
      </p>
    );
  }

  const label = micOpen
    ? t('jarvis-voice.listening')
    : status === 'thinking'
      ? t('jarvis-screen.thinking')
      : status === 'tool'
        ? t('jarvis-screen.toolRunning', { tool: tool ?? '' })
        : status === 'composing'
          ? t('jarvis-screen.composing')
          : null;

  if (label === null) {
    return null;
  }

  return (
    <p className="jarvis-status" role="status" data-kind={micOpen ? 'listening' : 'busy'}>
      <span className="jarvis-status-dot" aria-hidden="true" />
      {label}
    </p>
  );
};
