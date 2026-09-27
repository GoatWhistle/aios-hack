import { useI18n } from '@/shared/i18n/I18nContext';
import { activeScene } from '@/jarvis/model/scenes';
import { useJarvisSessionContext } from '@/jarvis/provider/contexts';
import { readRunSeries } from '@/jarvis/cards/payloads/runSeriesPayload';
import { RunSeriesPlot } from '@/jarvis/cards/RuleCard/RunSeriesPlot';
import { isRecord } from '@/jarvis/cards/payloads/payloadPrimitives';
import './JarvisCompanion.css';

export const JarvisCompanion = () => {
  const { t } = useI18n();
  const { companionVisible, hideCompanion, open, scenes } = useJarvisSessionContext();
  const scene = activeScene(scenes);
  if (!companionVisible || scene === null) return null;
  const chart = scene.cards
    .map((entry) => isRecord(entry.card.payload) ? entry.card.payload : null)
    .find((payload) => payload !== null && isRecord(payload.run_series)) ?? null;
  const series = chart === null ? null : readRunSeries(chart.run_series);

  return (
    <aside className="jarvis-companion" aria-label={t('jarvis-screen.companionLabel')}>
      <header className="jarvis-companion-head">
        <strong>{t('jarvis-screen.companionTitle')}</strong>
        <button type="button" onClick={hideCompanion} aria-label={t('jarvis-screen.companionClose')}>
          ×
        </button>
      </header>
      <p className="jarvis-companion-question">{scene.question}</p>
      <p className="jarvis-companion-answer">{scene.caption ?? scene.captionDraft}</p>
      {series === null ? null : (
        <RunSeriesPlot series={series} step={typeof chart?.step === 'number' ? chart.step : undefined} />
      )}
      <footer className="jarvis-companion-foot">
        <span>{t('jarvis-screen.companionEvidence', { count: String(scene.cards.length) })}</span>
        <button type="button" onClick={open}>{t('jarvis-screen.companionReopen')}</button>
      </footer>
    </aside>
  );
};
