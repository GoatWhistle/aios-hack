import { DASH, formatCalendarDate, formatPercent, formatQuantity } from '@/shared/lib/format';
import { useI18n } from '@/shared/i18n/I18nContext';
import { readWellList } from '@/jarvis/cards/payloads';
import { metricLabelKey } from '@/jarvis/cards/lib/metricLabel';
import { EmptyPayload } from '@/jarvis/cards/EmptyPayload/EmptyPayload';
import './WellListCard.css';

const barShare = (value: number, extreme: number): number =>
  extreme === 0 ? 0 : Math.min(1, Math.abs(value) / Math.abs(extreme));

export const WellListCard = ({ payload }: { payload: unknown }) => {
  const { lang, t } = useI18n();
  const listing = readWellList(payload);
  if (listing === null) {
    return <EmptyPayload />;
  }
  const labelKey = metricLabelKey(listing.by);
  const metricLabel = labelKey === null ? listing.by : t(`jarvis-cards.${labelKey}`);
  const extreme = listing.rows.reduce(
    (peak, row) => (Math.abs(row.value) > Math.abs(peak) ? row.value : peak),
    0
  );

  return (
    <div>
      {listing.period === 'whole_horizon' ? (
        <p className="jarvis-list-period">{t('jarvis-cards.listWholeHorizon')}</p>
      ) : listing.step === null && listing.date === null ? null : (
        <p className="jarvis-list-period">
          {listing.step === null
            ? DASH
            : t('jarvis-cards.listAtStep', {
                step: listing.step,
                date: listing.date === null ? DASH : formatCalendarDate(lang, listing.date)
              })}
        </p>
      )}
      {listing.total_count <= listing.rows.length ? null : (
        <p className="jarvis-list-period">
          {t('jarvis-cards.listShowingOf', {
            shown: listing.rows.length,
            total: listing.total_count
          })}
        </p>
      )}
      <ol className="jarvis-list">
      {listing.rows.map((row) => (
        <li className="jarvis-list-row" key={row.well} data-sign={row.value < 0 ? 'down' : 'up'}>
          <span className="jarvis-list-well">{row.well}</span>
          <span className="jarvis-list-bar" aria-hidden="true">
            <span
              className="jarvis-list-bar-fill"
              style={{ inlineSize: `${barShare(row.value, extreme) * 100}%` }}
            />
          </span>
          <span className="jarvis-list-value">{formatQuantity(lang, row.value, listing.unit, 3)}</span>
          <span className="jarvis-list-share">
            {row.share === null ? DASH : formatPercent(lang, row.share)}
          </span>
        </li>
      ))}
      <li className="jarvis-list-legend">
        <span>{metricLabel}</span>
        <span>{t('jarvis-cards.listShare')}</span>
      </li>
      </ol>
    </div>
  );
};
