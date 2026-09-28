import { useEffect, useRef, useState } from 'react';
import { useJarvisSessionContext } from '@/jarvis/provider/contexts';

export type SpherePose = 'resting' | 'perched';

export const useSpherePose = (): SpherePose => {
  const { scenes, sessionId } = useJarvisSessionContext();
  const asked = scenes.scenes.some((scene) => scene.question.length > 0);
  const spoken = asked || scenes.status !== null;
  const [pose, setPose] = useState<SpherePose>(() => (spoken ? 'perched' : 'resting'));
  const flownFor = useRef<string | null>(spoken ? sessionId : null);

  useEffect(() => {
    if (!spoken) {
      flownFor.current = null;
      setPose('resting');
      return;
    }
    if (flownFor.current === sessionId) {
      return;
    }
    flownFor.current = sessionId;
    setPose('perched');
  }, [spoken, sessionId]);

  return pose;
};
