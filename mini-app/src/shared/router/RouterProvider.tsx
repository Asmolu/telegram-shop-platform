import React from 'react';
import { prefetchRouteForPath } from './routePrefetch';
import { getMotionAwareScrollBehavior } from '../utils/motion';

type NavigateOptions = {
  replace?: boolean;
};

type RouterContextValue = {
  currentPath: string;
  pathname: string;
  searchParams: URLSearchParams;
  navigate: (to: string, options?: NavigateOptions) => void;
  goBack: (fallback?: string) => void;
};

const RouterContext = React.createContext<RouterContextValue | null>(null);
const HISTORY_INDEX_KEY = '__telegramShopIndex';
const SWIPE_EDGE_WIDTH = 32;
const SWIPE_MIN_DISTANCE = 72;
const SWIPE_MAX_VERTICAL_DISTANCE = 48;
const SWIPE_FINISH_DURATION = 190;
const SWIPE_CANCEL_DURATION = 220;
const SWIPE_UNDERLAY_CLASS = 'swipe-back-underlay';
const SWIPE_BACK_IGNORE_SELECTOR = [
  '[data-swipe-back-ignore]',
  '[role="dialog"][aria-modal="true"]',
  'input',
  'textarea',
  'select',
  '[contenteditable="true"]',
  '.banner-carousel__track',
  '.vertical-banner-grid',
  '.product-image-carousel__track',
  '.variant-carousel',
  '.related-products-carousel',
  '.aggressive-popup__track',
  '.chip-row',
  '.feed-chips',
  '.sort-row',
  '.tab-row',
  '.segmented-control',
].join(',');
const SWIPE_BACK_SURFACE_SELECTOR = '#root > .mini-app-frame, #root > .launch-screen';

function getCurrentPath() {
  return `${window.location.pathname}${window.location.search}`;
}

function getHistoryIndex() {
  const index = window.history.state?.[HISTORY_INDEX_KEY];
  return typeof index === 'number' && Number.isFinite(index) ? index : 0;
}

function createSwipeBackSnapshot() {
  const frame = document.querySelector<HTMLElement>(SWIPE_BACK_SURFACE_SELECTOR);
  if (!frame) {
    return null;
  }

  const underlay = document.createElement('div');
  const snapshot = frame.cloneNode(true) as HTMLElement;
  const scrollTop = Math.max(window.scrollY, 0);
  underlay.className = SWIPE_UNDERLAY_CLASS;
  underlay.setAttribute('aria-hidden', 'true');
  underlay.setAttribute('inert', '');
  snapshot.classList.add('swipe-back-underlay__snapshot');
  snapshot.style.setProperty('--swipe-back-snapshot-y', `-${scrollTop}px`);
  snapshot.querySelectorAll('[id]').forEach((element) => element.removeAttribute('id'));
  underlay.appendChild(snapshot);
  return underlay;
}

function mountSwipeBackSnapshot(snapshot: HTMLElement | null) {
  if (!snapshot || snapshot.isConnected) {
    return;
  }

  document.body.appendChild(snapshot);
}

function clearSwipeBackVisual() {
  const root = document.documentElement;
  root.removeAttribute('data-swipe-back-state');
  root.style.removeProperty('--swipe-back-x');
  root.style.removeProperty('--swipe-back-progress');
  root.style.removeProperty('--swipe-back-underlay-opacity');
  root.style.removeProperty('--swipe-back-underlay-scale');
  root.style.removeProperty('--swipe-back-underlay-x');
  document.querySelectorAll(`.${SWIPE_UNDERLAY_CLASS}`).forEach((element) => element.remove());
}

export function RouterProvider({ children }: { children: React.ReactNode }) {
  const [location, setLocation] = React.useState(getCurrentPath);
  const historyIndexRef = React.useRef(getHistoryIndex());
  const previousPageSnapshotRef = React.useRef<HTMLElement | null>(null);

  React.useEffect(() => {
    if (window.history.state?.[HISTORY_INDEX_KEY] === undefined) {
      window.history.replaceState(
        { ...(window.history.state ?? {}), [HISTORY_INDEX_KEY]: historyIndexRef.current },
        '',
        getCurrentPath(),
      );
    }
  }, []);

  React.useEffect(() => {
    const onPopState = () => {
      clearSwipeBackVisual();
      previousPageSnapshotRef.current = null;
      historyIndexRef.current = getHistoryIndex();
      setLocation(getCurrentPath());
    };
    window.addEventListener('popstate', onPopState);
    return () => window.removeEventListener('popstate', onPopState);
  }, []);

  const navigate = React.useCallback((to: string, options: NavigateOptions = {}) => {
    if (to === getCurrentPath()) {
      return;
    }

    if (options.replace) {
      window.history.replaceState(
        { ...(window.history.state ?? {}), [HISTORY_INDEX_KEY]: historyIndexRef.current },
        '',
        to,
      );
    } else {
      previousPageSnapshotRef.current?.remove();
      previousPageSnapshotRef.current = createSwipeBackSnapshot();
      historyIndexRef.current += 1;
      window.history.pushState({ [HISTORY_INDEX_KEY]: historyIndexRef.current }, '', to);
    }

    setLocation(getCurrentPath());
    window.scrollTo({ top: 0, behavior: getMotionAwareScrollBehavior() });
  }, []);

  const goBack = React.useCallback((fallback = '/main') => {
    if (historyIndexRef.current > 0) {
      window.history.back();
      return;
    }

    if (getCurrentPath() !== fallback) {
      window.history.replaceState(
        { ...(window.history.state ?? {}), [HISTORY_INDEX_KEY]: 0 },
        '',
        fallback,
      );
      historyIndexRef.current = 0;
      setLocation(getCurrentPath());
      window.scrollTo({ top: 0, behavior: getMotionAwareScrollBehavior() });
    }
  }, []);

  React.useEffect(() => {
    let animationFrame = 0;
    let finishTimer = 0;
    let gesture:
      | {
          startX: number;
          startY: number;
          latestX: number;
          latestY: number;
          startedAt: number;
        }
      | null = null;

    const setSwipeOffset = (offset: number) => {
      window.cancelAnimationFrame(animationFrame);
      animationFrame = window.requestAnimationFrame(() => {
        const safeOffset = Math.max(offset, 0);
        const progress = Math.min(safeOffset / Math.max(window.innerWidth, 1), 1);
        document.documentElement.style.setProperty('--swipe-back-x', `${safeOffset}px`);
        document.documentElement.style.setProperty('--swipe-back-progress', String(progress));
        document.documentElement.style.setProperty(
          '--swipe-back-underlay-opacity',
          String(0.98 + progress * 0.02),
        );
        document.documentElement.style.setProperty(
          '--swipe-back-underlay-scale',
          String(0.97 + progress * 0.03),
        );
        document.documentElement.style.setProperty(
          '--swipe-back-underlay-x',
          `${-18 + progress * 18}px`,
        );
      });
    };

    const resetGesture = () => {
      gesture = null;
    };

    const cancelGesture = () => {
      if (!gesture) {
        return;
      }

      resetGesture();
      document.documentElement.dataset.swipeBackState = 'cancel';
      setSwipeOffset(0);
      window.clearTimeout(finishTimer);
      finishTimer = window.setTimeout(clearSwipeBackVisual, SWIPE_CANCEL_DURATION);
    };

    const onTouchStart = (event: TouchEvent) => {
      const touch = event.touches[0];
      const target = event.target instanceof Element ? event.target : null;
      const currentPath = getCurrentPath();
      if (
        event.touches.length !== 1
        || !touch
        || touch.clientX > SWIPE_EDGE_WIDTH
        || (historyIndexRef.current <= 0 && (currentPath === '/' || currentPath === '/main'))
        || target?.closest(SWIPE_BACK_IGNORE_SELECTOR)
        || document.querySelector('[role="dialog"][aria-modal="true"]')
      ) {
        resetGesture();
        return;
      }

      window.clearTimeout(finishTimer);
      clearSwipeBackVisual();
      mountSwipeBackSnapshot(previousPageSnapshotRef.current);
      gesture = {
        startX: touch.clientX,
        startY: touch.clientY,
        latestX: touch.clientX,
        latestY: touch.clientY,
        startedAt: Date.now(),
      };
    };

    const onTouchMove = (event: TouchEvent) => {
      const touch = event.touches[0];
      if (!gesture || event.touches.length !== 1 || !touch) {
        return;
      }

      gesture.latestX = touch.clientX;
      gesture.latestY = touch.clientY;
      const deltaX = gesture.latestX - gesture.startX;
      const deltaY = Math.abs(gesture.latestY - gesture.startY);

      if (deltaX < -8 || deltaY > SWIPE_MAX_VERTICAL_DISTANCE) {
        cancelGesture();
        return;
      }

      if (deltaX > 14 && deltaX > deltaY * 1.5) {
        event.preventDefault();
        document.documentElement.dataset.swipeBackState = 'tracking';
        setSwipeOffset(Math.min(deltaX, window.innerWidth));
      }
    };

    const onTouchEnd = () => {
      if (!gesture) {
        return;
      }

      const deltaX = gesture.latestX - gesture.startX;
      const deltaY = Math.abs(gesture.latestY - gesture.startY);
      const duration = Date.now() - gesture.startedAt;
      const shouldGoBack = deltaX >= SWIPE_MIN_DISTANCE
        && deltaY <= SWIPE_MAX_VERTICAL_DISTANCE
        && deltaX > deltaY * 1.5
        && duration <= 900;

      if (shouldGoBack) {
        resetGesture();
        document.documentElement.dataset.swipeBackState = 'complete';
        setSwipeOffset(window.innerWidth);
        window.clearTimeout(finishTimer);
        finishTimer = window.setTimeout(() => {
          goBack();
          window.setTimeout(clearSwipeBackVisual, 40);
        }, SWIPE_FINISH_DURATION);
        return;
      }

      cancelGesture();
    };

    document.addEventListener('touchstart', onTouchStart, { passive: true });
    document.addEventListener('touchmove', onTouchMove, { passive: false });
    document.addEventListener('touchend', onTouchEnd, { passive: true });
    document.addEventListener('touchcancel', cancelGesture, { passive: true });

    return () => {
      window.cancelAnimationFrame(animationFrame);
      window.clearTimeout(finishTimer);
      clearSwipeBackVisual();
      document.removeEventListener('touchstart', onTouchStart);
      document.removeEventListener('touchmove', onTouchMove);
      document.removeEventListener('touchend', onTouchEnd);
      document.removeEventListener('touchcancel', cancelGesture);
    };
  }, [goBack]);

  const value = React.useMemo(() => {
    const url = new URL(location, window.location.origin);
    return {
      currentPath: `${url.pathname}${url.search}`,
      pathname: url.pathname,
      searchParams: url.searchParams,
      navigate,
      goBack,
    };
  }, [goBack, location, navigate]);

  return <RouterContext.Provider value={value}>{children}</RouterContext.Provider>;
}

export function useRouter() {
  const context = React.useContext(RouterContext);
  if (!context) {
    throw new Error('useRouter must be used within RouterProvider');
  }

  return context;
}

export function Link({
  to,
  className,
  children,
  title,
}: {
  to: string;
  className?: string;
  children: React.ReactNode;
  title?: string;
}) {
  const { navigate } = useRouter();
  const prefetch = React.useCallback(() => {
    prefetchRouteForPath(to, (pathname) => (pathname === '/' ? 'launch' : getRouteId(pathname)));
  }, [to]);

  return (
    <a
      className={className}
      href={to}
      title={title}
      onFocus={prefetch}
      onPointerEnter={prefetch}
      onTouchStart={prefetch}
      onClick={(event) => {
        event.preventDefault();
        navigate(to);
      }}
    >
      {children}
    </a>
  );
}

export function getRouteId(pathname: string) {
  if (pathname === '/' || pathname === '/main') {
    return 'main';
  }
  if (pathname === '/categories') {
    return 'categories';
  }
  if (pathname.startsWith('/category/')) {
    return 'category-detail';
  }
  if (pathname === '/search') {
    return 'search';
  }
  if (pathname === '/search/results') {
    return 'search-results';
  }
  if (pathname.startsWith('/product/')) {
    return 'product-detail';
  }
  if (pathname === '/cart') {
    return 'cart';
  }
  if (pathname === '/checkout') {
    return 'checkout';
  }
  if (pathname.startsWith('/order-success/')) {
    return 'order-success';
  }
  if (pathname.startsWith('/payment/')) {
    return 'payment';
  }
  if (pathname === '/profile') {
    return 'profile';
  }
  if (pathname === '/profile/personal-data') {
    return 'personal-data';
  }
  if (pathname === '/faq') {
    return 'faq';
  }
  return 'not-found';
}

export function getNumericRouteParam(pathname: string, prefix: string) {
  const raw = pathname.replace(prefix, '').split('/')[0];
  const value = Number(raw);
  return Number.isFinite(value) ? value : null;
}

export function getSafeReturnTo(value: string | null | undefined, fallback = '/main') {
  if (!value || value.startsWith('//') || !value.startsWith('/') || value.includes('\\')) {
    return fallback;
  }

  try {
    const url = new URL(value, window.location.origin);
    if (url.origin !== window.location.origin || getRouteId(url.pathname) === 'not-found') {
      return fallback;
    }

    const path = `${url.pathname}${url.search}`;
    return path === '/' ? fallback : path;
  } catch {
    return fallback;
  }
}

export function withReturnTo(to: string, returnTo: string | null | undefined) {
  const safeReturnTo = getSafeReturnTo(returnTo, '');
  if (!safeReturnTo) {
    return to;
  }

  const url = new URL(to, window.location.origin);
  url.searchParams.set('returnTo', safeReturnTo);
  return `${url.pathname}${url.search}`;
}

export function getAuthPath(returnTo: string | null | undefined) {
  return withReturnTo('/', returnTo);
}
