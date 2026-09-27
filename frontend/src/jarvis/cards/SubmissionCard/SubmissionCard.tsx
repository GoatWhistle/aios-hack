import { DASH, formatQuantity } from '@/shared/lib/format';
import { useI18n } from '@/shared/i18n/I18nContext';
import { readSubmission } from '@/jarvis/cards/payloads/submissionPayload';
import { runStatusLabel } from '@/jarvis/cards/lib/runStatusLabel';
import { EmptyPayload } from '@/jarvis/cards/EmptyPayload/EmptyPayload';
import './SubmissionCard.css';

const yesNo = (value: boolean | null, t: (key: string) => string) =>
  value === null ? DASH : t(value ? 'jarvis-cards.yes' : 'jarvis-cards.no');

const submissionFieldLabel = (field: string, t: (key: string) => string): string => {
  const key = `jarvis-cards.submissionField.${field}`;
  const translated = t(key);
  return translated === key ? field : translated;
};

export const SubmissionCard = ({ payload }: { payload: unknown }) => {
  const { lang, t } = useI18n();
  const bundle = readSubmission(payload);
  if (bundle === null) return <EmptyPayload />;
  return (
    <div className="jarvis-submission-card">
      <p className="jarvis-submission-run">{bundle.run_id} · {runStatusLabel(bundle.status, t)}</p>
      <p><strong>{t(bundle.assembled ? 'jarvis-cards.submissionAssembled' : 'jarvis-cards.submissionMissing')}</strong></p>
      {bundle.reason ? (
        <p title={bundle.reason}>
          {bundle.code === 'no-submission' ? t('jarvis-cards.submissionReason.noSubmission') : bundle.reason}
        </p>
      ) : null}
      {bundle.claimed_npv_rub === null ? null : <p>{t('jarvis-cards.submissionClaimedNpv')}: {formatQuantity(lang, bundle.claimed_npv_rub, 'RUB')}</p>}
      {bundle.checks ? (
        <ul>
          <li>{t('jarvis-cards.submissionReady')}: {yesNo(bundle.checks.status_ready_to_submit, t)}</li>
          <li>{t('jarvis-cards.submissionSchedule')}: {yesNo(bundle.checks.schedule_include_present, t)}</li>
          <li>{t('jarvis-cards.submissionSourceRun')}: {yesNo(bundle.checks.source_run_matches, t)}</li>
          <li>{t('jarvis-cards.submissionScheduleHash')}: {yesNo(bundle.checks.schedule_hash_matches, t)}</li>
          {bundle.checks.missing_fields.length ? (
            <li>
              {t('jarvis-cards.submissionMissingFields')}:{' '}
              {bundle.checks.missing_fields.map((field, index) => (
                <span key={`${field}-${index}`} title={field}>
                  {index > 0 ? ', ' : ''}{submissionFieldLabel(field, t)}
                </span>
              ))}
            </li>
          ) : null}
        </ul>
      ) : null}
    </div>
  );
};
