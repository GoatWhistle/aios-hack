import { formatNumber, formatQuantity } from '@/shared/lib/format';
import { useI18n } from '@/shared/i18n/I18nContext';
import type { AlternativeProposal, CaseProposal } from '@/jarvis/cards/RunProposalCard/proposalPayload';

export const CaseSummary = ({ proposal }: { proposal: CaseProposal }) => {
  const t = useI18n().t;
  const sectionLabel = proposal.section === 'injection_limits'
    ? t('jarvis-cards.proposalInjection')
    : proposal.section === 'liquid_limits'
      ? t('jarvis-cards.proposalLiquid')
      : proposal.section ?? '';
  const unitLabel = proposal.unit === 'm3/day'
    ? t('jarvis-cards.proposalRateUnit')
    : proposal.unit ?? '';

  return (
    <>
      <p>{t('jarvis-cards.proposalCaseSource', { scenario: proposal.scenario })}</p>
      <p>{proposal.request}</p>
      <p>{proposal.operation === 'add_well_outage'
        ? t('jarvis-cards.proposalOutage', {
            well: proposal.well ?? '',
            from: proposal.date_from ?? '',
            to: proposal.date_to ?? ''
          })
        : t('jarvis-cards.proposalLimit', {
            section: sectionLabel,
            year: proposal.year ?? '',
            before: proposal.before ?? t('jarvis-cards.proposalUnset'),
            after: proposal.after ?? '',
            unit: unitLabel
          })}</p>
    </>
  );
};

export const AlternativeSummary = ({ proposal }: { proposal: AlternativeProposal }) => {
  const { lang, t } = useI18n();

  return (
    <>
      <p>{t('jarvis-cards.proposalAlternativeSource', { run: proposal.source_run_id })}</p>
      <p>{t('jarvis-cards.proposalAlternativeAction', {
        well: proposal.action.well,
        from: proposal.action.from_step,
        through: proposal.action.through_step,
        before: formatNumber(lang, proposal.action.original_target_m3_per_day, 2),
        after: formatNumber(lang, proposal.action.alternative_target_m3_per_day, 2)
      })}</p>
      <p>{t('jarvis-cards.proposalAlternativeCost', {
        count: proposal.additional_opm_evaluations,
        npv: formatQuantity(lang, proposal.source_npv_rub, 'RUB')
      })}</p>
    </>
  );
};
