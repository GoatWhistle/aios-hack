import { useEffect, useState, type CSSProperties } from 'react';
import { useT } from '@/shared/i18n/I18nContext';
import type { ConsoleAction } from '@/jarvis/actions/lib/consoleAction';
import { Card } from '@/jarvis/cards/Card/Card';
import { CardBody } from '@/jarvis/cards/CardBody/CardBody';
import type { SceneCard } from '@/jarvis/model/scenes';
import { fullRowSeats } from '@/jarvis/scene/Orbit/orbitRows';
import './Orbit.css';

interface OrbitProps {
  cards: readonly SceneCard[];
  onOpen: (action: ConsoleAction) => void;
  briefingLoading?: boolean;
}

const WIDE_TYPES = new Set(['run-list', 'compare', 'series', 'well-comparison', 'field-map', 'system-map']);
const STAGGER_CAP = 6;

export const Orbit = ({ cards, onOpen, briefingLoading = false }: OrbitProps) => {
  const t = useT();
  const [expanded, setExpanded] = useState<string | null>(null);
  const proposalId = cards.find((entry) =>
    entry.card.type === 'case-proposal' || entry.card.type === 'alternative-proposal'
  )?.id;
  const firstId = cards[0]?.id;
  useEffect(() => {
    setExpanded(proposalId ?? firstId ?? null);
  }, [proposalId, firstId]);

  const rows = fullRowSeats(
    cards.map((entry) => ({ wide: WIDE_TYPES.has(entry.card.type), open: expanded === entry.id }))
  );

  return (
    <div
      className="jarvis-orbit"
      aria-label={t('jarvis-rail.orbitLabel')}
      role="group"
    >
      {cards.map((entry, index) => {
        const open = expanded === entry.id;
        const spansRow = rows[index] === true;
        const style = {
          '--orbit-step': Math.min(index, STAGGER_CAP)
        } as CSSProperties;
        return (
          <div
            className="jarvis-orbit-seat"
            key={entry.id}
            style={style}
            data-open={open ? 'true' : undefined}
            data-wide={WIDE_TYPES.has(entry.card.type) ? 'true' : undefined}
            data-full={spansRow ? 'true' : undefined}
          >
            <Card
              card={entry.card}
              expanded={open}
              onToggle={() => setExpanded(open ? null : entry.id)}
              onOpenInConsole={() => {
                if (entry.card.action !== undefined) {
                  onOpen(entry.card.action);
                }
              }}
            >
              <CardBody card={entry.card} onOpen={onOpen} briefingLoading={briefingLoading} />
            </Card>
          </div>
        );
      })}
    </div>
  );
};
