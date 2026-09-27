import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { I18nProvider } from '@/shared/i18n/I18nContext';
import { Card } from '@/jarvis/cards/Card/Card';

describe('Card provenance label', () => {
  it('shows a localized source category while preserving the exact provenance as detail', () => {
    window.localStorage.setItem('aios-lang', 'ru');
    const props = {
      card: { type: 'well' as const, title: 'Скважина 13', payload: {}, provenance: 'synthetic-demo' },
      expanded: false,
      onToggle: () => undefined,
      onOpenInConsole: () => undefined,
      children: <p>Данные карточки</p>
    };
    const view = render(<I18nProvider><Card {...props} /></I18nProvider>);

    const chip = screen.getByText('Демо');
    expect(chip.getAttribute('title')).toBe('synthetic-demo');
    expect(chip.getAttribute('aria-label')).toContain('synthetic-demo');

    view.unmount();
    window.localStorage.setItem('aios-lang', 'en');
    render(<I18nProvider><Card {...props} /></I18nProvider>);
    expect(screen.getByText('Demo')).toBeTruthy();
    window.localStorage.setItem('aios-lang', 'ru');
  });

  it('identifies a policy replay without presenting it as a missing source', () => {
    window.localStorage.setItem('aios-lang', 'en');
    const props = {
      card: {
        type: 'council' as const,
        title: 'Council step',
        payload: {},
        provenance: 'policy-hierarchy-replay'
      },
      expanded: false,
      onToggle: () => undefined,
      onOpenInConsole: () => undefined,
      children: <p>Replayed policy decision</p>
    };

    render(<I18nProvider><Card {...props} /></I18nProvider>);

    const chip = screen.getByText('Policy replay');
    expect(chip.getAttribute('title')).toBe('policy-hierarchy-replay');
    expect(chip.getAttribute('aria-label')).toContain('Source: policy replay');
  });
});
