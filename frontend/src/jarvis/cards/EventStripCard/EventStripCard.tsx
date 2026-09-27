import { formatCalendarDate } from '@/shared/lib/format';
import { useI18n } from '@/shared/i18n/I18nContext';
import { readEventStrip } from '@/jarvis/cards/payloads';
import { EmptyPayload } from '@/jarvis/cards/EmptyPayload/EmptyPayload';
import './EventStripCard.css';
import { clamp01 } from '@/shared/lib/math/clamp';

const EVENT_KEYS: Record<string, string> = {
  COMMISSIONED: 'jarvis-cards.eventCommissioned',
  ROLE_CHANGE: 'jarvis-cards.eventRoleChange',
  SHUT: 'jarvis-cards.eventShut'
};

export const eventPosition = (step: number, from: number, to: number): number => {
  const span = to - from;
  if (span <= 0) {
    return 0;
  }
  return clamp01((step - from) / span);
};

export const EventStripCard = ({ payload }: { payload: unknown }) => {
  const { lang, t } = useI18n();
  const strip = readEventStrip(payload);
  if (strip === null) {
    return <EmptyPayload />;
  }
  const kinds = [...new Set(strip.events.map((event) => event.type))];

  return (
    <div className="jarvis-events">
      <p className="jarvis-events-count">
        <span>{t('jarvis-cards.eventsCount')}</span>
        <span className="jarvis-events-total">{strip.events.length}</span>
      </p>
      {strip.events.length === 0 ? (
        <p className="jarvis-events-empty">
          {t('jarvis-cards.noEventsInRange', {
            from: strip.from_date === null ? `${t('jarvis-cards.step')} ${strip.from_step}` : formatCalendarDate(lang, strip.from_date),
            to: strip.to_date === null ? `${t('jarvis-cards.step')} ${strip.to_step}` : formatCalendarDate(lang, strip.to_date)
          })}
        </p>
      ) : (
        <>
          <div className="jarvis-events-strip">
            {strip.events.map((event) => (
              <span
                key={`${event.step}:${event.well}:${event.type}`}
                className="jarvis-events-mark"
                data-type={event.type}
                style={{
                  insetInlineStart: `${eventPosition(event.step, strip.from_step, strip.to_step) * 100}%`
                }}
                title={`${event.well} · ${formatCalendarDate(lang, event.date)}`}
              />
            ))}
          </div>
          <ul className="jarvis-events-legend">
            {kinds.map((kind) => (
              <li key={kind}>
                <span className="jarvis-events-swatch" data-type={kind} aria-hidden="true" />
                {EVENT_KEYS[kind] === undefined ? kind : t(EVENT_KEYS[kind])}
              </li>
            ))}
          </ul>
          <details className="jarvis-events-details">
            <summary>{t('jarvis-cards.eventDetails')}</summary>
            <ol>
              {strip.events.map((event) => (
                <li key={`${event.step}:${event.well}:${event.type}`}>
                  {formatCalendarDate(lang, event.date)} · {t('jarvis-cards.step')} {event.step} · {t('jarvis-cards.well')} {event.well} · {EVENT_KEYS[event.type] === undefined ? event.type : t(EVENT_KEYS[event.type])}
                </li>
              ))}
            </ol>
          </details>
        </>
      )}
    </div>
  );
};
