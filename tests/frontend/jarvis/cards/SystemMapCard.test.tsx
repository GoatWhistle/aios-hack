import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import { I18nProvider } from '@/shared/i18n/I18nContext';
import { SystemMapCard } from '@/jarvis/cards/SystemMapCard/SystemMapCard';

const payload = {
  focus: 'ui',
  total_nodes: 2,
  total_edges: 0,
  edges: [],
  nodes: [
    { id: 'ui', label: 'Console', kind: 'ui', summary: 'Console summary' },
    { id: 'custom', label: 'Custom', kind: 'external-kind', summary: 'Custom summary' }
  ]
};

afterEach(() => cleanup());

describe('SystemMapCard', () => {
  it('localizes known node kinds and preserves unknown kinds', () => {
    window.localStorage.setItem('aios-lang', 'ru');
    const { unmount } = render(<I18nProvider><SystemMapCard payload={payload} onOpen={() => undefined} /></I18nProvider>);
    expect(screen.getByText('Интерфейс')).toBeTruthy();
    unmount();

    window.localStorage.setItem('aios-lang', 'en');
    render(<I18nProvider><SystemMapCard payload={payload} onOpen={() => undefined} /></I18nProvider>);
    expect(screen.getByText('User interface')).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'Custom' }));
    expect(screen.getByText('external-kind')).toBeTruthy();
  });
});
