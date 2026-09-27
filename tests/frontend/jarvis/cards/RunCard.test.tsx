import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { I18nProvider } from '@/shared/i18n/I18nContext';
import { RunCard } from '@/jarvis/cards/RunCard/RunCard';

describe('RunCard conclusion export', () => {
  let clipboardDescriptor: PropertyDescriptor | undefined;
  let createUrlDescriptor: PropertyDescriptor | undefined;
  let revokeUrlDescriptor: PropertyDescriptor | undefined;

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
    if (clipboardDescriptor === undefined) delete (navigator as unknown as Record<string, unknown>).clipboard;
    else Object.defineProperty(navigator, 'clipboard', clipboardDescriptor);
    if (createUrlDescriptor === undefined) delete (URL as unknown as Record<string, unknown>).createObjectURL;
    else Object.defineProperty(URL, 'createObjectURL', createUrlDescriptor);
    if (revokeUrlDescriptor === undefined) delete (URL as unknown as Record<string, unknown>).revokeObjectURL;
    else Object.defineProperty(URL, 'revokeObjectURL', revokeUrlDescriptor);
  });

  it('copies and downloads the recorded Markdown conclusion', async () => {
    const markdown = '# Recorded conclusion\n\nOPM passed.';
    const writeText = vi.fn().mockResolvedValue(undefined);
    clipboardDescriptor = Object.getOwnPropertyDescriptor(navigator, 'clipboard');
    createUrlDescriptor = Object.getOwnPropertyDescriptor(URL, 'createObjectURL');
    revokeUrlDescriptor = Object.getOwnPropertyDescriptor(URL, 'revokeObjectURL');
    Object.defineProperty(navigator, 'clipboard', {
      configurable: true,
      value: { writeText }
    });
    const createObjectURL = vi.fn().mockReturnValue('blob:run-conclusion');
    const revokeObjectURL = vi.fn();
    Object.defineProperty(URL, 'createObjectURL', { configurable: true, value: createObjectURL });
    Object.defineProperty(URL, 'revokeObjectURL', { configurable: true, value: revokeObjectURL });
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => undefined);

    render(<I18nProvider><RunCard payload={{
      run_id: 'run-17', status: 'verified', conclusion_markdown: markdown,
      violations: [
        { kind: 'WATERCUT_LIMIT_EXCEEDED', detail: 'recorded violation' },
        { kind: 'CUSTOM_IDENTITY_FAILURE', detail: 'unknown identity' },
        { kind: 'dynamic-violations', detail: '165 total; 165 blocking' }
      ]
    }} /></I18nProvider>);
    expect(screen.getByText('проверен на OPM')).toBeTruthy();
    expect(screen.getByText('Превышен лимит обводнённости')).toBeTruthy();
    expect(screen.getByText('CUSTOM_IDENTITY_FAILURE')).toBeTruthy();
    expect(screen.getByText('Всего: 165; блокируют: 165')).toBeTruthy();
    fireEvent.click(screen.getByText('Инженерное заключение'));
    fireEvent.click(screen.getByRole('button', { name: 'Копировать' }));

    await waitFor(() => expect(screen.getByRole('button', { name: 'Скопировано' })).toBeTruthy());
    expect(writeText).toHaveBeenCalledWith(markdown);
    fireEvent.click(screen.getByRole('button', { name: 'Скачать Markdown' }));
    expect(createObjectURL).toHaveBeenCalledWith(expect.any(Blob));
    expect(click).toHaveBeenCalledTimes(1);
    expect(revokeObjectURL).toHaveBeenCalledWith('blob:run-conclusion');

  });
});
