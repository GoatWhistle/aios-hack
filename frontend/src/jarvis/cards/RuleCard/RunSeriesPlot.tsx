import { useMemo } from 'react';
import { formatNumber, formatStepDate, formatUnit } from '@/shared/lib/format';
import { useI18n } from '@/shared/i18n/I18nContext';
import type { RunSeriesPayload } from '@/jarvis/cards/payloads/runSeriesPayload';
import './RunSeriesPlot.css';

const linesOf = (values: readonly (number | null)[], min: number, max: number): string[] => {
  const span = max - min || 1;
  const lines: string[] = [];
  let points: string[] = [];
  values.forEach((value, index) => {
    if (value === null) {
      if (points.length > 0) lines.push(points.join(' '));
      points = [];
      return;
    }
    points.push(`${(index / Math.max(values.length - 1, 1) * 100).toFixed(2)},${(48 - ((value - min) / span) * 42).toFixed(2)}`);
  });
  if (points.length > 0) lines.push(points.join(' '));
  return lines;
};

export const RunSeriesPlot = ({ series, step }: { series: RunSeriesPayload; step?: number }) => {
  const { lang, t } = useI18n();
  const rows = series.rows;
  const input = rows.map((row) => row.input_rate);
  const scheduled = rows.map((row) => row.scheduled_rate);
  const values = [...input, ...scheduled].filter((value): value is number => value !== null && Number.isFinite(value));
  const minValue = values.length === 0 ? 0 : Math.min(...values);
  const maxValue = values.length === 0 ? 1 : Math.max(...values);
  const padding = maxValue === minValue ? Math.max(Math.abs(maxValue) * 0.05, 0.5) : (maxValue - minValue) * 0.06;
  const min = minValue - padding;
  const max = maxValue + padding;
  const inputLines = useMemo(() => linesOf(input, min, max), [input, min, max]);
  const scheduleLines = useMemo(() => linesOf(scheduled, min, max), [scheduled, min, max]);
  const first = rows[0];
  const last = rows[rows.length - 1];
  const currentIndex = step === undefined ? -1 : rows.findIndex((row) => row.step === step);
  const currentX = currentIndex < 0 ? null : currentIndex / Math.max(rows.length - 1, 1) * 100;

  return (
    <div className="jarvis-run-series" data-run={series.run_id} data-well={series.well}>
      <svg className="jarvis-run-series-plot" viewBox="0 0 100 52" preserveAspectRatio="none" role="img" aria-label={t('jarvis-cards.runSeriesAria', { run: series.run_id, well: series.well })}>
        <line x1="0" x2="100" y1="49" y2="49" className="jarvis-run-series-axis" />
        {currentX === null ? null : <line x1={currentX} x2={currentX} y1="2" y2="49" className="jarvis-run-series-current" />}
        {inputLines.map((line, index) => <polyline key={`input-${index}`} points={line} className="jarvis-run-series-input" />)}
        {scheduleLines.map((line, index) => <polyline key={`schedule-${index}`} points={line} className="jarvis-run-series-scheduled" />)}
      </svg>
      <div className="jarvis-run-series-legend">
        <span data-series="input">{t('jarvis-cards.runSeriesInput')}</span>
        <span data-series="scheduled">{t('jarvis-cards.runSeriesScheduled')}</span>
        <span className="jarvis-run-series-unit">{formatUnit(lang, series.unit)}</span>
      </div>
      <div className="jarvis-run-series-dates">
        <span>{formatStepDate(lang, first.date)}</span>
        <span>{formatStepDate(lang, last.date)}</span>
      </div>
      {currentIndex < 0 ? null : (
        <p className="jarvis-run-series-current-value">
          {formatStepDate(lang, rows[currentIndex].date)} · {t('jarvis-screen.contextStep')} {rows[currentIndex].step} · {t('jarvis-cards.runSeriesScheduled')}: {rows[currentIndex].scheduled_rate === null ? '—' : `${formatNumber(lang, rows[currentIndex].scheduled_rate, 2)} ${t('jarvis-cards.flowUnit')}`}
        </p>
      )}
      <small>{t('jarvis-cards.runSeriesScope')}</small>
    </div>
  );
};
