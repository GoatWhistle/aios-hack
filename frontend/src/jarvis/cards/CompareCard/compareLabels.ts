import { DASH } from '@/shared/lib/format';
import type { useI18n } from '@/shared/i18n/I18nContext';
import type { readCompare } from '@/jarvis/cards/payloads';
import type { CompareConstraints, CompareStatus } from '@/jarvis/cards/payloads/payloadTypes';
import { translationOrRaw } from '@/jarvis/cards/lib/translationFallback';

type Translate = ReturnType<typeof useI18n>['t'];

export const flagKeys = (status: CompareStatus): { key: string; on: boolean }[] => {
  const collected: { key: string; on: boolean }[] = [];
  if (status.sound !== null) {
    collected.push({ key: 'jarvis-cards.compareSound', on: status.sound });
  }
  if (status.converged !== null) {
    collected.push({ key: 'jarvis-cards.compareConverged', on: status.converged });
  }
  if (status.self_consistent !== null) {
    collected.push({ key: 'jarvis-cards.compareConsistent', on: status.self_consistent });
  }
  if (status.has_submission !== null) {
    collected.push({ key: 'jarvis-cards.compareSubmitted', on: status.has_submission });
  }
  return collected;
};

export const constraintCount = (constraints: CompareConstraints): string =>
  constraints.total === null ? DASH : String(constraints.total);

export const constraintGroupLabel = (key: string, t: Translate): string => {
  const translationKey = `jarvis-cards.compareConstraintGroup.${key}`;
  const translated = t(translationKey);
  return translated === translationKey ? key : translated;
};

export const economicLineLabel = (key: string, t: Translate): string => {
  const translationKey = `jarvis-cards.economicLine.${key}`;
  const translated = t(translationKey);
  return translated === translationKey ? key : translated;
};

export const reasonLabel = (
  reason: string,
  category: 'economic' | 'production',
  t: Translate
): string => {
  const known: Record<string, string> = category === 'economic' ? {
    'one or both runs have no recorded economics/npv-table.json': 'missingTable',
    'the recorded NPV table has no annual line items': 'noAnnualLines'
  } : {
    'one or both runs have no observation/<schedule_hash>/response.json': 'missingResponse',
    'an observation response has no interval_response rows': 'missingIntervalRows',
    'the OPM responses share no well/control_step rows': 'noSharedWellStep'
  };
  const key = known[reason];
  return key === undefined ? reason : translationOrRaw(`jarvis-cards.compareReason.${category}.${key}`, reason, t);
};

export const missingWellBreakdownLabel = (reason: string, t: Translate): string => {
  const match = /^no-comparison: run (.+) has no comparison\.json file, so the breakdown of the difference by well is unknown$/.exec(reason);
  return match === null ? reason : t('jarvis-cards.compareReason.missingWellBreakdown', { run: match[1] });
};

export const comparabilityNote = (
  comparability: NonNullable<ReturnType<typeof readCompare>>['comparability'],
  t: Translate
): string => {
  if (comparability === null || comparability.missing_fields === null || comparability.mismatched_fields === null) {
    return comparability?.note ?? '';
  }
  const fields = (items: string[]) => items.map((field) => translationOrRaw(`jarvis-cards.compareField.${field}`, field, t)).join(', ');
  if (comparability.mismatched_fields.length > 0) {
    return t('jarvis-cards.compareMismatchNote', { fields: fields(comparability.mismatched_fields) });
  }
  if (comparability.missing_fields.length > 0) {
    return t('jarvis-cards.compareMissingNote', { fields: fields(comparability.missing_fields) });
  }
  return t('jarvis-cards.compareMatchedNote');
};
