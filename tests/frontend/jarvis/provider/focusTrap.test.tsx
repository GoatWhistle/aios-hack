import { useRef } from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { focusableWithin, useFocusTrap } from '@/jarvis/provider/useFocusTrap';
import { useCloseBehaviour } from '@/features/inspector/ui/useCloseBehaviour';

describe('Jarvis focus ownership', () => {
  it('Escape closes Jarvis without also dismissing the selected well behind it', () => {
    const closeJarvis = vi.fn();
    const clearWell = vi.fn();
    const Harness = () => {
      const ref = useRef<HTMLDivElement>(null);
      useFocusTrap(ref, true, closeJarvis);
      useCloseBehaviour(true, clearWell);
      return <div ref={ref}><textarea aria-label="Question" /></div>;
    };
    render(<Harness />);
    fireEvent.keyDown(screen.getByRole('textbox'), { key: 'Escape' });
    expect(closeJarvis).toHaveBeenCalledOnce();
    expect(clearWell).not.toHaveBeenCalled();
  });

  it('does not trap focus on closed settings or hidden controls', () => {
    const root = document.createElement('div');
    root.innerHTML = '<button>Visible</button><div hidden><button>Hidden</button></div>'
      + '<details><summary>Settings</summary><button>Voice</button></details>'
      + '<div inert><button>Behind dialog</button></div>';
    document.body.append(root);
    expect(focusableWithin(root).map((node) => node.textContent)).toEqual(['Visible', 'Settings']);
    root.remove();
  });
});
