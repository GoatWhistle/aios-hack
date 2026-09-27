import { useEffect, useRef, useState } from 'react';
import { loadJson, readCachedJson } from '@/shared/api/jsonCache';
import type { ResourceState } from '@/shared/api/ResourceState';
import { ResourceNotFoundError } from '@/shared/api/fetchJson';

const initialStateFor = <T,>(
  url: string | null,
  validate: (data: unknown) => data is T
): ResourceState<T> => {
  if (url === null) {
    return { status: 'loading' };
  }
  const cached = readCachedJson(url, validate);
  return cached === null ? { status: 'loading' } : { status: 'ready', data: cached };
};

export const useJsonResource = <T,>(
  url: string | null,
  validate: (data: unknown) => data is T
): ResourceState<T> => {
  const [resource, setResource] = useState(() => ({
    url,
    state: initialStateFor(url, validate)
  }));
  const state = resource.url === url
    ? resource.state
    : initialStateFor(url, validate);
  const validateRef = useRef(validate);
  validateRef.current = validate;

  useEffect(() => {
    if (url === null) {
      setResource({ url, state: { status: 'loading' } });
      return;
    }
    let cancelled = false;
    const check = validateRef.current;
    const cached = readCachedJson(url, check);
    if (cached !== null) {
      setResource({ url, state: { status: 'ready', data: cached } });
      return;
    }
    setResource({ url, state: { status: 'loading' } });
    loadJson(url, check)
      .then((data) => {
        if (!cancelled) {
          setResource({ url, state: { status: 'ready', data } });
        }
      })
      .catch((error: unknown) => {
        if (!cancelled) {
          setResource({
            url,
            state: {
              status: 'error',
              ...(error instanceof ResourceNotFoundError ? { notFound: true } : {})
            }
          });
        }
      });
    return () => {
      cancelled = true;
    };
  }, [url]);

  return state;
};
