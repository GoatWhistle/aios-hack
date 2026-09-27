import { describe, expect, it } from 'vitest';
import { DASH, formatCalendarDate, formatNumber, formatPercent, formatQuantity, formatStepDate, formatTimestamp, formatUnit } from '@/shared/lib/format/format';

describe('formatCalendarDate', () => {
  it('uses a localized day, month, and year while preserving UTC dates', () => {
    expect(formatCalendarDate('en', '2007-01-01')).toBe('Jan 1, 2007');
    expect(formatCalendarDate('ru', '2007-01-01')).toContain('2007');
    expect(formatCalendarDate('ru', '2007-01-01')).not.toBe('2007-01-01');
  });

  it('returns a dash for an invalid date', () => {
    expect(formatCalendarDate('en', 'not-a-date')).toBe(DASH);
  });
});

describe('formatTimestamp', () => {
  it('formats date and time in a stable UTC timezone', () => {
    expect(formatTimestamp('en', '2025-01-02T03:04:00Z')).toMatch(/Jan 2, 2025/);
    expect(formatTimestamp('en', '2025-01-02T03:04:00Z')).toMatch(/3:04/);
    expect(formatTimestamp('ru', '2025-01-02T03:04:00Z')).toContain('2025');
  });

  it('returns a dash for an invalid timestamp', () => {
    expect(formatTimestamp('en', 'not-a-timestamp')).toBe(DASH);
  });
});

describe('formatUnit', () => {
  it('uses one localized display for flow rates across legacy spellings', () => {
    for (const unit of ['m3/day', 'm³/day', 'm³/сут']) {
      expect(formatUnit('ru', unit)).toBe('м³/сут');
      expect(formatUnit('en', unit)).toBe('m³/day');
    }
  });

  it('localizes common dimensionless, pressure, and count units', () => {
    expect(formatUnit('ru', 'fraction')).toBe('доля');
    expect(formatUnit('en', 'bar')).toBe('bar');
    expect(formatUnit('ru', 'wells')).toBe('скважин');
    expect(formatUnit('en', 'records')).toBe('records');
  });

  it('covers every unit emitted by Jarvis metrics, constraints, and comparison cards', () => {
    const emittedUnits: Record<string, [string, string]> = {
      RUB: ['руб.', 'RUB'],
      'm3/day': ['м³/сут', 'm³/day'],
      bar: ['бар', 'bar'],
      fraction: ['доля', 'fraction'],
      wells: ['скважин', 'wells'],
      steps: ['шагов', 'steps'],
      records: ['записей', 'records'],
      kg: ['кг', 'kg'],
      m3: ['м³', 'm³'],
      'RUB/m3': ['руб./м³', 'RUB/m³'],
      'RUB/t': ['руб./т', 'RUB/t'],
      't/m3': ['т/м³', 't/m³'],
      't/day': ['т/сут', 't/day'],
      months: ['мес.', 'months'],
      years: ['лет', 'years'],
      coefficient: ['коэффициент', 'coefficient']
    };
    for (const [unit, [ru, en]] of Object.entries(emittedUnits)) {
      expect(formatUnit('ru', unit), `Russian label for ${unit}`).toBe(ru);
      expect(formatUnit('en', unit), `English label for ${unit}`).toBe(en);
    }
  });

  it('localizes currency units for concise quantities', () => {
    expect(formatQuantity('ru', 1250, 'RUB')).toMatch(/1 250 руб\./);
    expect(formatQuantity('en', 1250, 'rub')).toBe('1,250 RUB');
  });

  it('preserves specialized units it does not recognize', () => {
    expect(formatUnit('ru', 'kg/m³')).toBe('kg/m³');
  });
});

describe('formatStepDate', () => {
  it('keeps the calendar month of a UTC midnight date', () => {
    expect(formatStepDate('en', '2007-01-01')).toBe('January 2007');
    expect(formatStepDate('ru', '2007-01-01')).toBe('январь 2007 г.');
  });

  it('does not drift for dates across the year boundary', () => {
    expect(formatStepDate('en', '2025-01-01')).toBe('January 2025');
    expect(formatStepDate('en', '2024-12-01')).toBe('December 2024');
  });

  it('formats every month without shifting', () => {
    const months = Array.from({ length: 12 }, (_, index) =>
      formatStepDate('en', `2007-${String(index + 1).padStart(2, '0')}-01`)
    );
    expect(months).toEqual([
      'January 2007',
      'February 2007',
      'March 2007',
      'April 2007',
      'May 2007',
      'June 2007',
      'July 2007',
      'August 2007',
      'September 2007',
      'October 2007',
      'November 2007',
      'December 2007'
    ]);
  });

  it('returns a dash for an invalid date instead of throwing', () => {
    expect(formatStepDate('ru', '')).toBe(DASH);
    expect(formatStepDate('ru', 'not-a-date')).toBe(DASH);
    expect(formatStepDate('en', '2007-13-45')).toBe(DASH);
    expect(() => formatStepDate('en', '')).not.toThrow();
  });
});

describe('formatNumber', () => {
  it('renders a value rounding to zero without a minus sign', () => {
    expect(formatNumber('ru', -0.4, 0)).toBe('0');
    expect(formatNumber('en', -0.4, 0)).toBe('0');
    expect(formatNumber('ru', -0, 0)).toBe('0');
    expect(formatNumber('en', -0.04, 1)).toBe('0');
  });

  it('keeps genuine negative values negative', () => {
    expect(formatNumber('en', -0.5, 0)).toBe('-1');
    expect(formatNumber('en', -1.4, 0)).toBe('-1');
    expect(formatNumber('en', -0.05, 1)).toBe('-0.1');
    expect(formatNumber('en', -0.5, 1)).toBe('-0.5');
  });

  it('keeps positive values unchanged', () => {
    expect(formatNumber('en', 0.4, 0)).toBe('0');
    expect(formatNumber('en', 1.6, 0)).toBe('2');
  });
});

describe('formatPercent', () => {
  it('formats a share as a percentage', () => {
    expect(formatPercent('en', 0.5)).toBe('50%');
  });
});

describe('numbers that are not there', () => {
  it('refuses to print a value it does not have as if it were zero', () => {
    expect(formatNumber('ru', null as unknown as number)).toBe(DASH);
    expect(formatNumber('ru', undefined as unknown as number)).toBe(DASH);
    expect(formatNumber('ru', NaN)).toBe(DASH);
    expect(formatNumber('ru', Infinity)).toBe(DASH);
    expect(formatPercent('ru', NaN)).toBe(DASH);
    expect(formatNumber('ru', 0)).not.toBe(DASH);
  });

  it('collapses a negative zero the same way in both formatters', () => {
    expect(formatNumber('ru', -0)).toBe(formatNumber('ru', 0));
    expect(formatPercent('ru', -0)).toBe(formatPercent('ru', 0));
    expect(formatPercent('ru', -0.0000001)).toBe(formatPercent('ru', 0));
  });

});
