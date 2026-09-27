import { DASH, formatCalendarDate, formatQuantity } from '@/shared/lib/format';
import { useI18n } from '@/shared/i18n/I18nContext';
import { readCouncil } from '@/jarvis/cards/payloads';
import { councilCodeLabel } from '@/jarvis/cards/lib/councilCodeLabel';
import { EmptyPayload } from '@/jarvis/cards/EmptyPayload/EmptyPayload';
import './CouncilCard.css';

export const CouncilCard = ({ payload }: { payload: unknown }) => {
  const { lang, t } = useI18n();
  const council = readCouncil(payload);
  if (council === null) {
    return <EmptyPayload />;
  }

  return (
    <div className="jarvis-council">
      <p className="jarvis-council-when">
        {t('jarvis-screen.contextStep')} {council.step}
        {council.date === null ? '' : ` · ${formatCalendarDate(lang, council.date)}`}
        {council.group === null ? '' : ` · ${council.group}`}
      </p>
      <ol className="jarvis-council-levels">
        {council.levels.map((level) => (
          <li className="jarvis-council-level" key={`${level.rank}-${level.agent}`}>
            <span className="jarvis-council-rank">R{level.rank}</span>
            <span className="jarvis-council-agent">{councilCodeLabel('agent', level.agent, t)}</span>
            <span className="jarvis-council-verdict" data-verdict={level.verdict}>
              {councilCodeLabel('verdict', level.verdict, t)}
            </span>
            <span className="jarvis-council-bounds">
              {level.bounds.length === 0
                ? DASH
                : level.bounds.map((bound) => formatQuantity(lang, bound, 'm3/day', 1)).join(' → ')}
            </span>
            <span className="jarvis-council-decisions">
              {t('jarvis-cards.councilDecisions', { count: String(level.decisions) })}
            </span>
          </li>
        ))}
      </ol>
      {council.outcome.well === null && council.outcome.action === null ? null : (
        <p className="jarvis-council-outcome">
          <span className="jarvis-council-outcome-label">{t('jarvis-cards.councilOutcome')}</span>
          {council.outcome.well ?? DASH} · {councilCodeLabel('action', council.outcome.action, t)}
          {council.outcome.rule === null ? '' : ` · ${council.outcome.rule}`}
        </p>
      )}
      {council.agents_fired.length === 0 ? null : (
        <p className="jarvis-council-agents">
          {council.agents_fired.map((agent) => councilCodeLabel('agent', agent, t)).join(' · ')}
        </p>
      )}
    </div>
  );
};
