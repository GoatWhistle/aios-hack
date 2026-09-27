import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { I18nProvider } from '@/shared/i18n/I18nContext';
import { DocCard } from '@/jarvis/cards/DocCard/DocCard';

describe('DocCard', () => {
  it('labels the normalized search score and formats it for the active locale', () => {
    window.localStorage.setItem('aios-lang', 'ru');
    const payload = {
      hits: [{ source: 'method.md', score: 0.6, snippet: 'ЧДД', text: 'ЧДД' }],
      terms: ['ЧДД'], indexed_chunks: 10, indexed_files: 2
    };
    const view = render(<I18nProvider><DocCard payload={payload} /></I18nProvider>);

    expect(screen.getByText('поиск: 0,6')).toBeTruthy();
    expect(screen.getByText('поиск: 0,6').getAttribute('title')).toContain('не вероятность');

    view.unmount();
    window.localStorage.setItem('aios-lang', 'en');
    render(<I18nProvider><DocCard payload={payload} /></I18nProvider>);
    expect(screen.getByText('search score: 0.6')).toBeTruthy();
    window.localStorage.setItem('aios-lang', 'ru');
  });
});
