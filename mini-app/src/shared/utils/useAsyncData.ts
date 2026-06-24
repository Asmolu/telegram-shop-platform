import React from 'react';
import { isRequestAbortedError, toApiErrorMessage } from '../api';
import { useNetworkRetry } from '../network/NetworkProvider';

export function useAsyncData<T>(
  loader: () => Promise<T>,
  deps: React.DependencyList,
  initialValue: T | null = null,
) {
  const [data, setData] = React.useState<T | null>(initialValue);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);
  const [version, setVersion] = React.useState(0);

  React.useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);

    loader()
      .then((result) => {
        if (!cancelled) {
          setData(result);
        }
      })
      .catch((loadError: unknown) => {
        if (isRequestAbortedError(loadError)) {
          return;
        }
        if (!cancelled) {
          setError(toApiErrorMessage(loadError));
        }
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, version]);

  const reload = React.useCallback(() => setVersion((current) => current + 1), []);
  useNetworkRetry(reload);

  return { data, loading, error, reload, setData };
}
