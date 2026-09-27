import { useT } from '@/shared/i18n/I18nContext';
import { translateOr } from '@/jarvis/i18nFallback';
import { useOptionalJarvisSession } from '@/jarvis/provider/contexts';
import { readError } from '@/jarvis/cards/payloads';
import './ErrorCard.css';

export const ErrorCard = ({ payload }: { payload: unknown }) => {
  const t = useT();
  const jarvis = useOptionalJarvisSession();
  const failure = readError(payload);
  const toolKey = failure.tool === null ? null : `jarvis-cards.toolName.${failure.tool}`;
  const translatedTool = toolKey === null ? null : t(toolKey);
  const toolLabel = failure.tool === null
    ? null
    : translatedTool === toolKey
      ? failure.tool.replaceAll('_', ' ')
      : translatedTool;

  return (
    <div className="jarvis-error" role="status">
      <p className="jarvis-error-title">{t('jarvis-cards.errorTitle')}</p>
      <p className="jarvis-error-reason">
        {failure.message || translateOr(t, `jarvis-screen.error.${failure.code}`, 'jarvis-screen.error.unknown')}
      </p>
      {failure.next_step === null ? null : (
        <p className="jarvis-error-next-step">{failure.next_step}</p>
      )}
      {toolLabel === null ? null : <p className="jarvis-error-tool">{toolLabel}</p>}
      {jarvis === null ? null : (
        <button type="button" className="jarvis-error-retry" onClick={jarvis.retry}>
          {t('jarvis-screen.retry')}
        </button>
      )}
    </div>
  );
};
