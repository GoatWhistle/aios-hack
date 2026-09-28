import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { useHotkeys } from '@/features/timeline-player/model/useHotkeys';
import { useWorkspaceRouting } from '@/app/router/useWorkspaceRouting';
import { useCommandPalette } from '@/features/command-palette/ui/useCommandPalette';

const step = vi.fn();
const select = vi.fn();
const play = vi.fn();
const route = vi.fn();
const Harness = ({ modal = true }: { modal?: boolean }) => {
  useHotkeys({ steps: [], stepIndex: 0, onStep: step, onSelect: select, onTogglePlay: play });
  useWorkspaceRouting({ workspace: 'field', view: 'projection', setRoute: route });
  const palette = useCommandPalette();
  return <>
    {modal ? <section role="dialog" aria-modal="true"><details><summary>Settings</summary></details><button>Dialog action</button></section> : null}
    <button>Outside action</button>
    <p data-testid="palette-state">{palette.open ? 'open' : 'closed'}</p>
  </>;
};

describe('console hotkey isolation from Jarvis', () => {
  beforeEach(() => {
    window.history.replaceState({}, '', '/field/projection');
    step.mockClear(); select.mockClear(); play.mockClear(); route.mockClear();
  });

  it('never changes playback, step, or workspace while a modal dialog owns input', () => {
    render(<Harness />);
    route.mockClear();
    const summary = screen.getByText('Settings');
    const space = new KeyboardEvent('keydown', { key: ' ', code: 'Space', bubbles: true, cancelable: true });
    summary.dispatchEvent(space);
    expect(space.defaultPrevented).toBe(false);
    for (const key of ['ArrowLeft', 'ArrowRight', 'Home', 'End', '[', ']', '2']) fireEvent.keyDown(summary, { key });
    fireEvent.keyDown(window, { key: ' ' });
    fireEvent.keyDown(window, { key: '3' });
    expect(play).not.toHaveBeenCalled();
    expect(step).not.toHaveBeenCalled();
    expect(select).not.toHaveBeenCalled();
    expect(route).not.toHaveBeenCalled();
  });

  it('preserves native button activation and modifiers without a modal', () => {
    render(<Harness modal={false} />);
    route.mockClear();
    const space = new KeyboardEvent('keydown', { key: ' ', bubbles: true, cancelable: true });
    screen.getByText('Outside action').dispatchEvent(space);
    expect(space.defaultPrevented).toBe(false);
    for (const modifier of ['ctrlKey', 'metaKey', 'altKey']) {
      fireEvent.keyDown(window, { key: ' ', [modifier]: true });
      fireEvent.keyDown(window, { key: '2', [modifier]: true });
    }
    const handled = new KeyboardEvent('keydown', { key: ' ', bubbles: true, cancelable: true });
    handled.preventDefault();
    window.dispatchEvent(handled);
    expect(play).not.toHaveBeenCalled();
    expect(route).not.toHaveBeenCalled();
    fireEvent.keyDown(window, { key: ' ' });
    fireEvent.keyDown(window, { key: 'ArrowRight' });
    fireEvent.keyDown(window, { key: '2' });
    expect(play).toHaveBeenCalledOnce();
    expect(step).toHaveBeenCalledWith(1);
    expect(route).toHaveBeenCalledOnce();
  });

  it('cannot open another command modal over Jarvis but retains its own shortcut', () => {
    const { rerender } = render(<Harness />);
    fireEvent.keyDown(screen.getByText('Settings'), { key: 'k', ctrlKey: true });
    expect(screen.getByTestId('palette-state').textContent).toBe('closed');
    rerender(<Harness modal={false} />);
    fireEvent.keyDown(window, { key: 'k', ctrlKey: true });
    expect(screen.getByTestId('palette-state').textContent).toBe('open');
    fireEvent.keyDown(window, { key: 'k', ctrlKey: true });
    expect(screen.getByTestId('palette-state').textContent).toBe('closed');
  });
});
