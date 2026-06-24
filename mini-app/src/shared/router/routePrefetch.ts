import { getNetworkState } from '../network/networkState';

type RoutePrefetcher = () => Promise<unknown>;
type RouteIdResolver = (pathname: string) => string;

const routePrefetchers = new Map<string, RoutePrefetcher>();
const prefetchedRouteIds = new Set<string>();
const prefetchingRouteIds = new Set<string>();

type NavigatorWithConnection = Navigator & {
  connection?: {
    saveData?: boolean;
    effectiveType?: string;
  };
};

type WindowWithIdleCallback = Window & {
  requestIdleCallback?: (callback: () => void, options?: { timeout?: number }) => number;
  cancelIdleCallback?: (handle: number) => void;
};

export function registerRoutePrefetchers(prefetchers: Record<string, RoutePrefetcher>) {
  Object.entries(prefetchers).forEach(([routeId, prefetcher]) => {
    routePrefetchers.set(routeId, prefetcher);
  });
}

export function canPrefetchRoute() {
  if (typeof window === 'undefined' || typeof navigator === 'undefined') {
    return false;
  }

  if (getNetworkState() !== 'online') {
    return false;
  }

  const connection = (navigator as NavigatorWithConnection).connection;
  if (connection?.saveData) {
    return false;
  }

  const effectiveType = String(connection?.effectiveType ?? '').toLowerCase();
  return effectiveType !== 'slow-2g' && effectiveType !== '2g';
}

export function prefetchRouteById(routeId: string) {
  if (!canPrefetchRoute() || prefetchedRouteIds.has(routeId) || prefetchingRouteIds.has(routeId)) {
    return;
  }

  const prefetcher = routePrefetchers.get(routeId);
  if (!prefetcher) {
    return;
  }

  prefetchingRouteIds.add(routeId);
  void prefetcher()
    .then(() => {
      prefetchedRouteIds.add(routeId);
    })
    .catch(() => {
      // A speculative prefetch must never surface as UI failure.
    })
    .finally(() => {
      prefetchingRouteIds.delete(routeId);
    });
}

export function scheduleRoutePrefetch(routeId: string) {
  if (!canPrefetchRoute()) {
    return () => undefined;
  }

  const schedule = window as WindowWithIdleCallback;
  if (typeof schedule.requestIdleCallback === 'function') {
    const handle = schedule.requestIdleCallback(() => prefetchRouteById(routeId), { timeout: 1_500 });
    return () => schedule.cancelIdleCallback?.(handle);
  }

  const timer = window.setTimeout(() => prefetchRouteById(routeId), 450);
  return () => window.clearTimeout(timer);
}

export function prefetchRouteForPath(to: string, resolveRouteId: RouteIdResolver) {
  try {
    const url = new URL(to, window.location.origin);
    prefetchRouteById(resolveRouteId(url.pathname));
  } catch {
    // Ignore malformed or external hrefs. Navigation still owns validation.
  }
}

export function resetRoutePrefetchStateForTests() {
  prefetchedRouteIds.clear();
  prefetchingRouteIds.clear();
  routePrefetchers.clear();
}
