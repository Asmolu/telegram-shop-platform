import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  prefetchRouteById,
  registerRoutePrefetchers,
  resetRoutePrefetchStateForTests,
} from './routePrefetch';
import { setNetworkState } from '../network/networkState';

function setConnection(connection: { saveData?: boolean; effectiveType?: string } | undefined) {
  Object.defineProperty(navigator, 'connection', {
    configurable: true,
    value: connection,
  });
}

describe('route prefetch policy', () => {
  afterEach(() => {
    resetRoutePrefetchStateForTests();
    setNetworkState('online');
    setConnection(undefined);
    vi.restoreAllMocks();
  });

  it('skips speculative prefetch while offline, recovering, saving data, or on 2g', () => {
    const prefetcher = vi.fn().mockResolvedValue(undefined);
    registerRoutePrefetchers({ cart: prefetcher });

    setNetworkState('offline');
    prefetchRouteById('cart');
    setNetworkState('recovering');
    prefetchRouteById('cart');
    setNetworkState('online');
    setConnection({ saveData: true, effectiveType: '4g' });
    prefetchRouteById('cart');
    setConnection({ effectiveType: '2g' });
    prefetchRouteById('cart');

    expect(prefetcher).not.toHaveBeenCalled();
  });

  it('prefetches a registered route once on a normal online connection', async () => {
    const prefetcher = vi.fn().mockResolvedValue(undefined);
    registerRoutePrefetchers({ cart: prefetcher });
    setConnection({ effectiveType: '4g' });

    prefetchRouteById('cart');
    prefetchRouteById('cart');
    await Promise.resolve();

    expect(prefetcher).toHaveBeenCalledTimes(1);
  });
});
