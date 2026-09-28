import { useI18n } from '@/shared/i18n/I18nContext';
import { useJarvisSessionContext } from '@/jarvis/provider/contexts';
import type { SpherePose } from '@/jarvis/stage/SphereFlight/useSpherePose';
import './OfflineNotice.css';

interface OfflineNoticeProps {
  pose: SpherePose;
}

export const OfflineNotice = ({ pose }: OfflineNoticeProps) => {
  const { t } = useI18n();
  const { capabilities, retry } = useJarvisSessionContext();

  if (capabilities.ok) {
    return null;
  }

  const noKey = capabilities.failure === 'no-api-key';
  const title = noKey ? t('jarvis-screen.chipNoKey') : t('jarvis-screen.chipOffline');
  const reason = noKey ? t('jarvis-screen.noKeyReason') : t('jarvis-screen.offlineReason');

  return (
    <div className="jarvis-offline" role="alert" data-pose={pose} data-kind={noKey ? 'no-key' : 'unreachable'}>
      <p className="jarvis-offline-title">{title}</p>
      <p className="jarvis-offline-reason">{reason}</p>
      <button type="button" className="jarvis-offline-retry" onClick={retry}>
        {t('jarvis-screen.retry')}
      </button>
    </div>
  );
};
