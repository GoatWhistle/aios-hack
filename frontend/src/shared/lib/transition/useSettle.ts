import { useEffect, useRef, useState } from 'react';

export const useSettle = (key: unknown): boolean => {
  const [settling, setSettling] = useState(false);
  const first = useRef(true);

  useEffect(() => {
    if (first.current) {
      first.current = false;
      return;
    }
    setSettling(true);
    const frame = requestAnimationFrame(() => setSettling(false));
    return () => cancelAnimationFrame(frame);
  }, [key]);

  return settling;
};
