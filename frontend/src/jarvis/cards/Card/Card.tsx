import { useId, type ReactNode } from 'react';
import { CaretRightIcon } from '@phosphor-icons/react';
import { useT } from '@/shared/i18n/I18nContext';
import type { JarvisCard } from '@/jarvis/transport/events';
import { provenanceKindOf, provenanceTitleKey } from '@/jarvis/cards/payloads/provenance';
import { useSettle } from '@/shared/lib/transition/useSettle';
import './Card.css';

interface CardProps {
  card: JarvisCard;
  expanded: boolean;
  onToggle: () => void;
  onOpenInConsole: () => void;
  children: ReactNode;
}

export const Card = ({ card, expanded, onToggle, onOpenInConsole, children }: CardProps) => {
  const t = useT();
  const bodyId = useId();
  const settling = useSettle(expanded);
  const kind = provenanceKindOf(card.provenance);
  const chipLabel = kind === 'unknown' && card.provenance.trim().length > 0
    ? card.provenance
    : t(`jarvis-cards.provenanceKind.${kind}`);

  return (
    <article
      className="jarvis-card"
      role="group"
      aria-label={t('jarvis-cards.cardLabel', { title: card.title })}
      data-type={card.type}
      data-expanded={expanded ? 'true' : undefined}
      data-settling={settling ? 'true' : undefined}
    >
      <header className="jarvis-card-head">
        <h3 className="jarvis-card-title">{card.title}</h3>
        <span
          className="jarvis-card-chip"
          data-kind={kind}
          title={card.provenance}
          aria-label={`${t(provenanceTitleKey(kind))}: ${card.provenance}`}
        >
          {chipLabel}
        </span>
      </header>
      <div className="jarvis-card-body" id={bodyId}>{children}</div>
      <footer className="jarvis-card-foot">
        <button
          type="button"
          className="jarvis-card-toggle"
          aria-expanded={expanded}
          aria-controls={bodyId}
          aria-label={expanded ? t('jarvis-cards.collapse') : t('jarvis-cards.expand')}
          onClick={onToggle}
        >
          <CaretRightIcon size={14} weight="bold" aria-hidden="true" />
        </button>
        {card.action === undefined ? null : (
          <button type="button" className="jarvis-card-open" onClick={onOpenInConsole}>
            {card.action.companion_only ? t('jarvis-cards.openBesideConsole') : t('jarvis-cards.openInConsole')}
          </button>
        )}
      </footer>
    </article>
  );
};
