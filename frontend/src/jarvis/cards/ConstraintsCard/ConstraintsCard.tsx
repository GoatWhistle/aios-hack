import { DASH, formatNumber, formatUnit } from '@/shared/lib/format';
import { useI18n } from '@/shared/i18n/I18nContext';
import type { Lang } from '@/shared/i18n/dictionaries';
import { readConstraints } from '@/jarvis/cards/payloads';
import { EmptyPayload } from '@/jarvis/cards/EmptyPayload/EmptyPayload';
import type { ConstraintRow } from '@/jarvis/cards/payloads/payloadTypes';
import './ConstraintsCard.css';

const cellOf = (lang: Lang, row: ConstraintRow, t: ReturnType<typeof useI18n>['t']): string => {
  if (row.value === null) {
    return DASH;
  }
  if (typeof row.value === 'boolean') {
    return t(row.value ? 'jarvis-cards.yes' : 'jarvis-cards.no');
  }
  if (typeof row.value === 'number') {
    return formatNumber(lang, row.value, 3);
  }
  return row.value;
};

const localizedOrRaw = (
  t: ReturnType<typeof useI18n>['t'],
  prefix: string,
  value: string
): string => {
  const key = `jarvis-cards.${prefix}.${value}`;
  const translated = t(key);
  return translated === key ? value : translated;
};

export const ConstraintsCard = ({ payload }: { payload: unknown }) => {
  const { lang, t } = useI18n();
  const constraints = readConstraints(payload);
  if (constraints === null) {
    return <EmptyPayload />;
  }
  const groups = new Map<string, ConstraintRow[]>();
  for (const row of constraints.items) {
    const key = row.group ?? '';
    const bucket = groups.get(key);
    if (bucket === undefined) {
      groups.set(key, [row]);
      continue;
    }
    bucket.push(row);
  }

  return (
    <div className="jarvis-constraints">
      <p className="jarvis-constraints-case">{constraints.case}</p>
      {[...groups.entries()].map(([group, rows]) => (
        <section className="jarvis-constraints-group" key={group}>
          {group.length === 0 ? null : (
              <p className="jarvis-constraints-group-name">{localizedOrRaw(t, 'constraintGroup', group)}</p>
          )}
          <dl className="jarvis-constraints-list">
            {rows.map((row) => (
              <div key={row.key} data-empty={row.empty ? 'true' : undefined}>
                <dt>{localizedOrRaw(t, 'constraint', row.key)}</dt>
                <dd>
                  <span className="jarvis-constraints-value">{cellOf(lang, row, t)}</span>
                  {row.unit === null ? null : (
                    <span className="jarvis-constraints-unit">{formatUnit(lang, row.unit)}</span>
                  )}
                  {row.unit === null && typeof row.value === 'number' ? (
                    <span className="jarvis-constraints-unit">{t('jarvis-cards.unitNotSpecified')}</span>
                  ) : null}
                  {row.source === null ? null : (
                    <span className="jarvis-constraints-source">{localizedOrRaw(t, 'constraintSource', row.source)}</span>
                  )}
                </dd>
              </div>
            ))}
          </dl>
        </section>
      ))}
      <p className="jarvis-constraints-total">
        {t('jarvis-cards.constraintsTotal', { count: String(constraints.items.length) })}
      </p>
    </div>
  );
};
