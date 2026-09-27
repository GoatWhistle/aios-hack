import { Sparkline } from '@/shared/ui/Sparkline';
import { DASH, formatCalendarDate, formatPercent, formatQuantity } from '@/shared/lib/format';
import { useI18n } from '@/shared/i18n/I18nContext';
import { readWell } from '@/jarvis/cards/payloads';
import { provenanceKindOf } from '@/jarvis/cards/payloads/provenance';
import { EmptyPayload } from '@/jarvis/cards/EmptyPayload/EmptyPayload';
import { wellCodeLabel } from '@/jarvis/cards/lib/wellCodeLabel';
import './WellCard.css';

export const WellCard = ({ payload }: { payload: unknown }) => {
  const { lang, t } = useI18n();
  const well = readWell(payload);
  if (well === null) {
    return <EmptyPayload />;
  }
  const values = well.spark.map((point) => point.value);
  const rows: { key: string; label: string; value: string }[] = [
    { key: 'role', label: t('jarvis-cards.wellRole'), value: wellCodeLabel(well.role, 'role', t) },
    { key: 'availability', label: t('jarvis-cards.availability'), value: wellCodeLabel(well.availability, 'availability', t) },
    { key: 'status', label: t('jarvis-cards.wellStatus'), value: wellCodeLabel(well.operating_status, 'status', t) },
    {
      key: 'liquid',
      label: t('jarvis-cards.wellLiquid'),
      value: formatQuantity(lang, well.liquid_rate, 'm3/day', 1)
    },
    {
      key: 'injection',
      label: t('jarvis-cards.wellInjection'),
      value: formatQuantity(lang, well.injection_rate, 'm3/day', 1)
    },
    {
      key: 'watercut',
      label: t('jarvis-cards.wellWatercut'),
      value: well.watercut === null ? DASH : formatPercent(lang, well.watercut)
    },
    { key: 'bhp', label: t('jarvis-cards.wellBhp'), value: formatQuantity(lang, well.bhp, 'bar', 1) },
    { key: 'setpoint', label: t('jarvis-cards.wellSetpoint'), value: formatQuantity(lang, well.setpoint, 'm3/day', 1) },
    {
      key: 'npv',
      label: t('jarvis-cards.wholeHorizonNpv'),
      value: well.npv === null ? DASH : formatQuantity(lang, well.npv, 'RUB')
    }
  ];

  return (
    <div className="jarvis-well">
      {well.step === null && well.date === null ? null : (
        <p className="jarvis-well-context">
          {well.step === null ? '' : `${t('jarvis-cards.step')} ${well.step}`}
          {well.step !== null && well.date !== null ? ' · ' : ''}
          {well.date === null ? '' : formatCalendarDate(lang, well.date)}
        </p>
      )}
      <dl className="jarvis-well-rows">
        {rows.map((row) => (
          <div className="jarvis-well-row" key={row.key}>
            <dt>{row.label}</dt>
            <dd>{row.value.length === 0 ? DASH : row.value}</dd>
          </div>
        ))}
      </dl>
      <p className="jarvis-well-context" data-testid="well-npv-provenance" title={well.npv_provenance}>
        {t('jarvis-cards.wellNpvSource', { source: provenanceKindOf(well.npv_provenance) === 'unknown' ? well.npv_provenance : t(`jarvis-cards.provenanceKind.${provenanceKindOf(well.npv_provenance)}`) })}
        {well.npv_source_run_id ? ` · ${well.npv_source_run_id}` : ''}
      </p>
      {values.length === 0 ? null : (
        <Sparkline
          values={values}
          current={values.length - 1}
          label={t('jarvis-cards.wellLiquid')}
          stroke="var(--color-jarvis-body)"
          height={32}
        />
      )}
    </div>
  );
};
