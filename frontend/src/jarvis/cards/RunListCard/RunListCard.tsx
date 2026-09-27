import { DASH, formatCalendarDate, formatQuantity } from '@/shared/lib/format';
import { useI18n } from '@/shared/i18n/I18nContext';
import { readRunList } from '@/jarvis/cards/payloads';
import { runStatusLabel } from '@/jarvis/cards/lib/runStatusLabel';
import { runStrategyLabel } from '@/jarvis/cards/lib/runStrategyLabel';
import { useOptionalJarvisSession } from '@/jarvis/provider/contexts';
import { EmptyPayload } from '@/jarvis/cards/EmptyPayload/EmptyPayload';
import './RunListCard.css';

export const RunListCard = ({ payload }: { payload: unknown }) => {
  const { lang, t } = useI18n();
  const jarvis = useOptionalJarvisSession();
  const list = readRunList(payload);
  if (list === null) {
    return <EmptyPayload />;
  }

  const roleLabel = (role: string | null) => {
    if (role === null) return null;
    switch (role) {
      case 'submitted-plan': return t('jarvis-cards.scenarioRoleSubmittedPlan');
      case 'historical-repeat': return t('jarvis-cards.scenarioRoleHistoricalRepeat');
      case 'diagnostic-policy-run': return t('jarvis-cards.scenarioRoleDiagnostic');
      case 'candidate-experiment': return t('jarvis-cards.scenarioRoleCandidate');
      default: return role;
    }
  };

  return (
    <div className="jarvis-runs">
      <table className="jarvis-runs-table">
        <thead>
          <tr>
            <th scope="col">{t('jarvis-cards.runId')}</th>
            <th scope="col">{t('jarvis-cards.runManifestModified')}</th>
            <th scope="col">{t('jarvis-cards.runStatus')}</th>
            <th scope="col">{t('jarvis-cards.runNpv')}</th>
            {jarvis === null ? null : <th scope="col">{t('jarvis-cards.runSelection')}</th>}
          </tr>
        </thead>
        <tbody>
          {list.rows.map((row) => (
            <tr key={row.run_id} data-sound={row.sound === true ? 'true' : undefined}>
              <th scope="row">
                <span className="jarvis-runs-id">{row.run_id}</span>
                {roleLabel(row.scenario_role) === null ? null : (
                  <span className="jarvis-runs-strategy" title={row.scenario_role ?? undefined}>{roleLabel(row.scenario_role)}</span>
                )}
                {row.strategy === null ? null : (
                  <span className="jarvis-runs-strategy" title={row.strategy}>{runStrategyLabel(row.strategy, t)}</span>
                )}
                {row.generation_reasons_status === 'unavailable' ? (
                  <span className="jarvis-runs-strategy">{t('jarvis-cards.generationReasonsUnavailable')}</span>
                ) : row.generation_reasons_status === 'recorded-and-indexed' ? (
                  <span className="jarvis-runs-strategy">{t('jarvis-cards.generationReasonsAvailable')}</span>
                ) : null}
              </th>
              <td>
                {row.ts === '' ? t('jarvis-cards.noDateRecorded') : (
                  <time dateTime={row.ts}>{formatCalendarDate(lang, row.ts)}</time>
                )}
              </td>
              <td>{runStatusLabel(row.status, t)}</td>
              <td className="jarvis-runs-npv">
                {row.verified_npv === null
                  ? row.predicted_npv === null
                    ? DASH
                    : formatQuantity(lang, row.predicted_npv, 'RUB')
                  : formatQuantity(lang, row.verified_npv, 'RUB')}
              </td>
              {jarvis === null ? null : (
                <td>
                  <button
                    type="button"
                    className="jarvis-run-select"
                    aria-pressed={jarvis.askContext.run_id === row.run_id}
                    onClick={() => jarvis.selectRun(row.run_id)}
                  >
                    {jarvis.askContext.run_id === row.run_id
                      ? t('jarvis-cards.runSelected')
                      : t('jarvis-cards.selectRun')}
                  </button>
                </td>
              )}
            </tr>
          ))}
        </tbody>
      </table>
      <p className="jarvis-runs-total">{t('jarvis-cards.runTotal', { count: String(list.total) })}</p>
    </div>
  );
};
