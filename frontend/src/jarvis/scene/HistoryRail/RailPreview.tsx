import { useEffect, useLayoutEffect, useRef } from 'react';
import { useT } from '@/shared/i18n/I18nContext';
import './RailPreview.css';

export interface RailPreviewData {
  index: number;
  anchor: DOMRect;
  question: string;
  glyphs: readonly string[];
  caption: string;
  context: string;
}

interface RailPreviewProps {
  data: RailPreviewData | null;
}

const edgeOf = (node: HTMLElement): number => {
  const raw = getComputedStyle(node).getPropertyValue('--rail-preview-edge');
  const value = Number.parseFloat(raw);
  return Number.isFinite(value) ? value : 0;
};

export const RailPreview = ({ data }: RailPreviewProps) => {
  const t = useT();
  const ref = useRef<HTMLDivElement>(null);

  useLayoutEffect(() => {
    const node = ref.current;
    if (node === null) {
      return;
    }
    if (data === null) {
      node.hidePopover?.();
      return;
    }
    node.showPopover?.();
    const edge = edgeOf(node);
    const width = node.offsetWidth;
    const height = node.offsetHeight;
    const centre = data.anchor.left + data.anchor.width / 2 - width / 2;
    const left = Math.max(edge, Math.min(window.innerWidth - width - edge, centre));
    const above = data.anchor.top - height - edge;
    const top = above >= edge ? above : data.anchor.bottom + edge;
    node.style.setProperty('--rail-preview-left', `${Math.round(left)}px`);
    node.style.setProperty('--rail-preview-top', `${Math.round(top)}px`);
  }, [data]);

  useEffect(() => {
    const node = ref.current;
    return () => {
      node?.hidePopover?.();
    };
  }, []);

  return (
    <div ref={ref} className="jarvis-rail-preview" popover="manual" role="presentation">
      {data === null ? null : (
        <>
          <span className="jarvis-rail-preview-question">{data.question}</span>
          <span className="jarvis-rail-preview-glyphs" aria-hidden="true">
            {data.glyphs.length === 0 ? t('jarvis-rail.railNoCards') : data.glyphs.join(' ')}
          </span>
          {data.caption.length === 0 ? null : (
            <span className="jarvis-rail-preview-caption">{data.caption}</span>
          )}
          <span className="jarvis-rail-preview-context">{data.context}</span>
        </>
      )}
    </div>
  );
};
