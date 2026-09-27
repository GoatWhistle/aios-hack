import type { Lang } from '@/shared/i18n/I18nContext';

const locales: Record<Lang, string> = { ru: 'ru-RU', en: 'en-US' };

export const DASH = '—';

const localizedUnits: Record<string, Record<Lang, string>> = {
  'm3/day': { ru: 'м³/сут', en: 'm³/day' },
  'm³/day': { ru: 'м³/сут', en: 'm³/day' },
  'm³/сут': { ru: 'м³/сут', en: 'm³/day' },
  't/day': { ru: 'т/сут', en: 't/day' },
  'т/сут': { ru: 'т/сут', en: 't/day' },
  rub: { ru: 'руб.', en: 'RUB' },
  '₽': { ru: 'руб.', en: 'RUB' },
  kg: { ru: 'кг', en: 'kg' },
  m3: { ru: 'м³', en: 'm³' },
  'rub/m3': { ru: 'руб./м³', en: 'RUB/m³' },
  'rub/t': { ru: 'руб./т', en: 'RUB/t' },
  't/m3': { ru: 'т/м³', en: 't/m³' },
  fraction: { ru: 'доля', en: 'fraction' },
  coefficient: { ru: 'коэффициент', en: 'coefficient' },
  bar: { ru: 'бар', en: 'bar' },
  wells: { ru: 'скважин', en: 'wells' },
  steps: { ru: 'шагов', en: 'steps' },
  months: { ru: 'мес.', en: 'months' },
  years: { ru: 'лет', en: 'years' },
  records: { ru: 'записей', en: 'records' }
};

export const formatUnit = (lang: Lang, unit: string): string =>
  localizedUnits[unit.trim().toLowerCase()]?.[lang] ?? unit;

export const formatQuantity = (
  lang: Lang,
  value: number | null,
  unit: string,
  digits = 0
): string => {
  if (value === null || !Number.isFinite(value)) return DASH;
  const number = formatNumber(lang, value, digits);
  const label = unit.trim() === '' ? '' : formatUnit(lang, unit);
  return label === '' ? number : `${number} ${label}`;
};

const numberFormats = new Map<string, Intl.NumberFormat>();
const percentFormats = new Map<Lang, Intl.NumberFormat>();
const dateFormats = new Map<Lang, Intl.DateTimeFormat>();
const calendarDateFormats = new Map<Lang, Intl.DateTimeFormat>();
const timestampFormats = new Map<Lang, Intl.DateTimeFormat>();

const numberFormat = (lang: Lang, digits: number): Intl.NumberFormat => {
  const key = `${lang}:${digits}`;
  const cached = numberFormats.get(key);
  if (cached !== undefined) {
    return cached;
  }
  const format = new Intl.NumberFormat(locales[lang], { maximumFractionDigits: digits });
  numberFormats.set(key, format);
  return format;
};

const percentFormat = (lang: Lang): Intl.NumberFormat => {
  const cached = percentFormats.get(lang);
  if (cached !== undefined) {
    return cached;
  }
  const format = new Intl.NumberFormat(locales[lang], {
    style: 'percent',
    maximumFractionDigits: 1
  });
  percentFormats.set(lang, format);
  return format;
};

const dateFormat = (lang: Lang): Intl.DateTimeFormat => {
  const cached = dateFormats.get(lang);
  if (cached !== undefined) {
    return cached;
  }
  const format = new Intl.DateTimeFormat(locales[lang], {
    month: 'long',
    year: 'numeric',
    timeZone: 'UTC'
  });
  dateFormats.set(lang, format);
  return format;
};

const calendarDateFormat = (lang: Lang): Intl.DateTimeFormat => {
  const cached = calendarDateFormats.get(lang);
  if (cached !== undefined) {
    return cached;
  }
  const format = new Intl.DateTimeFormat(locales[lang], {
    dateStyle: 'medium',
    timeZone: 'UTC'
  });
  calendarDateFormats.set(lang, format);
  return format;
};

export const formatNumber = (lang: Lang, value: number, digits = 0): string => {
  if (!Number.isFinite(value)) {
    return DASH;
  }
  const format = numberFormat(lang, digits);
  const text = format.format(value);
  return text === format.format(-0) ? format.format(0) : text;
};

export const formatPercent = (lang: Lang, value: number): string => {
  if (!Number.isFinite(value)) {
    return DASH;
  }
  const format = percentFormat(lang);
  const text = format.format(value);
  return text === format.format(-0) ? format.format(0) : text;
};

export const formatStepDate = (lang: Lang, iso: string): string => {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) {
    return DASH;
  }
  return dateFormat(lang).format(date);
};

export const formatCalendarDate = (lang: Lang, iso: string): string => {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) {
    return DASH;
  }
  return calendarDateFormat(lang).format(date);
};

export const formatTimestamp = (lang: Lang, iso: string): string => {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) {
    return DASH;
  }
  let format = timestampFormats.get(lang);
  if (format === undefined) {
    format = new Intl.DateTimeFormat(locales[lang], {
      dateStyle: 'medium',
      timeStyle: 'short',
      timeZone: 'UTC'
    });
    timestampFormats.set(lang, format);
  }
  return format.format(date);
};
