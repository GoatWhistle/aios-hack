import { formatQuantity } from '@/shared/lib/format';
import type { Lang } from '@/shared/i18n/dictionaries';
import type { Translate } from '@/shared/i18n/I18nContext';
import { translationOrRaw } from '@/jarvis/cards/lib/translationFallback';

export const violationDetailLabel = (
  kind: string,
  detail: string,
  lang: Lang,
  t: Translate
): string => {
  if (kind === 'OPEN_WITHOUT_FLOW') {
    const match = /^the schedule keeps the well open with setpoint ([\d.]+) m3\/day, the response gives a zero rate; control mode ([A-Z_]+)$/.exec(detail);
    if (match !== null) {
      return t('jarvis-cards.violationDetail.openWithoutFlow', {
        setpoint: formatQuantity(lang, Number(match[1]), 'm3/day', 3),
        mode: translationOrRaw(`jarvis-cards.controlMode.${match[2]}`, match[2], t)
      });
    }
  }
  if (kind === 'BHP_LIMITED_WITHOUT_UNDERSHOOT'
    && detail === 'BHP_LIMITED mode while the target is reached: a pressure limit is claimed, but there is no shortfall') {
    return t('jarvis-cards.violationDetail.bhpTargetReached');
  }
  return detail;
};
