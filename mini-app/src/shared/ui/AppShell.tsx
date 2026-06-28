import React from 'react';
import { getBanners, getCart, trackBannerClick, type Banner } from '../api';
import { useAuth } from '../auth/AuthProvider';
import { NetworkBanner } from '../network/NetworkBanner';
import { useNetworkState } from '../network/NetworkProvider';
import { Link, useRouter } from '../router/RouterProvider';
import { getUserDisplayName } from '../utils/format';
import { normalizeAssetUrl } from '../utils/images';
import { getMotionAwareScrollBehavior } from '../utils/motion';
import { copyTextToClipboard, getBannerAction, getBannerCtaLabel } from '../utils/banners';
import { BackIcon } from './Icons';
import mensStyleLogo from '../assets/mens-style-logo.webp';

const navItems = [
  { to: '/main', label: 'Лента', icon: 'home', match: ['/main', '/'] },
  { to: '/categories', label: 'Категории', icon: 'grid', match: ['/categories', '/category'] },
  { to: '/search', label: 'Поиск', icon: 'search', match: ['/search', '/search/results'] },
  { to: '/cart?tab=cart', label: 'Корзина', icon: 'cart', match: ['/cart', '/checkout', '/order-success'] },
  { to: '/profile', label: 'Профиль', icon: 'profile', match: ['/profile'] },
] as const;

const AGGRESSIVE_POPUP_SESSION_KEY = 'telegram_shop_aggressive_popup_dismissed';
const POPUP_SESSION_KEY = 'telegram_shop_popup_dismissed';
const FLOATING_HELP_STORAGE_KEY = 'telegram_shop_order_help_widget_v1';
const FLOATING_HELP_MARGIN = 12;
const FLOATING_HELP_BOTTOM_GUARD = 104;
const FLOATING_HELP_DISMISS_DISTANCE = 80;
const FLOATING_HELP_DRAG_THRESHOLD = 8;
const FLOATING_HELP_THROW_VELOCITY = 0.45;
const FLOATING_HELP_DEFAULT_SIZE = { width: 216, height: 46 };
const FLOATING_HELP_TAB_SIZE = { width: 46, height: 62 };

type FloatingHelpHiddenSide = 'left' | 'right';
type FloatingHelpPosition = {
  x: number;
  y: number;
};
type FloatingHelpState = {
  hiddenSide: FloatingHelpHiddenSide | null;
  position: FloatingHelpPosition | null;
};
type FloatingHelpBounds = {
  minX: number;
  maxX: number;
  minY: number;
  maxY: number;
  width: number;
};

function isActive(pathname: string, item: (typeof navItems)[number]) {
  return item.match.some((path) => pathname === path || pathname.startsWith(`${path}/`));
}

function clampNumber(value: number, min: number, max: number) {
  if (max < min) {
    return min;
  }
  return Math.min(Math.max(value, min), max);
}

function normalizeStoredPosition(value: unknown): FloatingHelpPosition | null {
  if (!value || typeof value !== 'object') {
    return null;
  }

  const maybePosition = value as Partial<FloatingHelpPosition>;
  if (!Number.isFinite(maybePosition.x) || !Number.isFinite(maybePosition.y)) {
    return null;
  }

  return {
    x: Number(maybePosition.x),
    y: Number(maybePosition.y),
  };
}

function readFloatingHelpState(): FloatingHelpState {
  if (typeof window === 'undefined') {
    return { hiddenSide: null, position: null };
  }

  try {
    const rawValue = window.localStorage.getItem(FLOATING_HELP_STORAGE_KEY);
    if (!rawValue) {
      return { hiddenSide: null, position: null };
    }

    const parsed = JSON.parse(rawValue) as Partial<FloatingHelpState>;
    const hiddenSide = parsed.hiddenSide === 'left' || parsed.hiddenSide === 'right'
      ? parsed.hiddenSide
      : null;

    return {
      hiddenSide,
      position: normalizeStoredPosition(parsed.position),
    };
  } catch {
    return { hiddenSide: null, position: null };
  }
}

function writeFloatingHelpState(state: FloatingHelpState) {
  try {
    window.localStorage.setItem(
      FLOATING_HELP_STORAGE_KEY,
      JSON.stringify({
        hiddenSide: state.hiddenSide,
        position: state.position,
      }),
    );
  } catch {
    // localStorage can be unavailable in embedded or private browsing contexts.
  }
}

function getViewportRect() {
  const width = window.innerWidth || document.documentElement.clientWidth || 430;
  const height = window.innerHeight || document.documentElement.clientHeight || 720;
  return { left: 0, top: 0, right: width, bottom: height, width, height };
}

function getMiniAppFrameRect(element: HTMLElement | null) {
  const viewport = getViewportRect();
  const frame = element?.closest('.mini-app-frame') as HTMLElement | null
    ?? document.querySelector<HTMLElement>('.mini-app-frame');
  const rect = frame?.getBoundingClientRect();

  if (!rect || rect.width <= 0 || rect.height <= 0) {
    return viewport;
  }

  return {
    left: clampNumber(rect.left, viewport.left, viewport.right),
    top: clampNumber(rect.top, viewport.top, viewport.bottom),
    right: clampNumber(rect.right, viewport.left, viewport.right),
    bottom: clampNumber(rect.bottom, viewport.top, viewport.bottom),
    width: Math.min(rect.width, viewport.width),
    height: Math.min(rect.height, viewport.height),
  };
}

function getFloatingHelpBounds(
  element: HTMLElement | null,
  fallbackSize = FLOATING_HELP_DEFAULT_SIZE,
): FloatingHelpBounds {
  const rect = element?.getBoundingClientRect();
  const width = rect && rect.width > 0 ? rect.width : fallbackSize.width;
  const height = rect && rect.height > 0 ? rect.height : fallbackSize.height;
  const frameRect = getMiniAppFrameRect(element);
  const viewport = getViewportRect();
  const bottomEdge = Math.min(frameRect.bottom || viewport.bottom, viewport.bottom);
  const minX = frameRect.left + FLOATING_HELP_MARGIN;
  const maxX = Math.max(minX, frameRect.right - width - FLOATING_HELP_MARGIN);
  const minY = frameRect.top + FLOATING_HELP_MARGIN;
  const maxY = Math.max(minY, bottomEdge - height - FLOATING_HELP_BOTTOM_GUARD);

  return { minX, maxX, minY, maxY, width };
}

function getDefaultFloatingHelpPosition(element: HTMLElement | null) {
  const bounds = getFloatingHelpBounds(element);
  return { x: bounds.maxX, y: bounds.maxY };
}

function clampFloatingHelpPosition(
  position: FloatingHelpPosition,
  element: HTMLElement | null,
) {
  const bounds = getFloatingHelpBounds(element);
  return {
    x: clampNumber(position.x, bounds.minX, bounds.maxX),
    y: clampNumber(position.y, bounds.minY, bounds.maxY),
  };
}

function shouldShowFloatingHelp(path: string) {
  const pathname = path.split('?')[0] || '/';
  return pathname === '/'
    || pathname === '/main'
    || pathname === '/categories'
    || pathname.startsWith('/category')
    || pathname === '/search'
    || pathname.startsWith('/search/');
}

function getFloatingHelpDismissSide({
  deltaX,
  elapsedMs,
  position,
  bounds,
}: {
  deltaX: number;
  elapsedMs: number;
  position: FloatingHelpPosition;
  bounds: FloatingHelpBounds;
}): FloatingHelpHiddenSide | null {
  const velocityX = deltaX / Math.max(elapsedMs, 1);
  const thrownLeft = velocityX <= -FLOATING_HELP_THROW_VELOCITY && deltaX < -36;
  const thrownRight = velocityX >= FLOATING_HELP_THROW_VELOCITY && deltaX > 36;
  const pushedLeft = position.x <= bounds.minX + 4 && deltaX < -FLOATING_HELP_DISMISS_DISTANCE;
  const pushedRight = position.x >= bounds.maxX - 4 && deltaX > FLOATING_HELP_DISMISS_DISTANCE;

  if (thrownLeft || pushedLeft) {
    return 'left';
  }
  if (thrownRight || pushedRight) {
    return 'right';
  }
  return null;
}

export function BrandMark({ className = '' }: { className?: string }) {
  return (
    <span className={`brand-mark ${className}`.trim()} aria-hidden="true">
      <img src={mensStyleLogo} alt="" />
    </span>
  );
}

export function TopBar({
  title,
  onBack,
  backFallback = '/main',
  hideBack = false,
  right,
  children,
  variant = 'marketplace',
}: {
  title: string;
  onBack?: () => void;
  backFallback?: string;
  hideBack?: boolean;
  right?: React.ReactNode;
  children?: React.ReactNode;
  variant?: 'marketplace' | 'feed';
}) {
  const { pathname, goBack } = useRouter();
  const showBack = !hideBack && pathname !== '/' && pathname !== '/main';
  const handleBack = onBack ?? (() => goBack(backFallback));
  const isFeed = variant === 'feed';
  const className = `top-bar top-bar--marketplace${isFeed ? ' top-bar--feed' : ''}`;

  return (
    <header className={className}>
      <div className="top-bar__main">
        {isFeed ? (
          <>
            <div className="top-bar__left top-bar__left--edge">
              {showBack ? (
                <button className="icon-button top-bar__back-button" type="button" aria-label="Назад" onClick={handleBack}>
                  <BackIcon />
                </button>
              ) : (
                <span className="top-bar__edge-spacer" aria-hidden="true" />
              )}
            </div>
            <div className="top-bar__brand-lockup">
              <BrandMark />
              <h1>{title}</h1>
            </div>
            <div className="top-bar__right">{right}</div>
          </>
        ) : (
          <>
            <div className="top-bar__left">
              {showBack ? (
                <button className="icon-button top-bar__back-button" type="button" aria-label="Назад" onClick={handleBack}>
                  <BackIcon />
                </button>
              ) : null}
              <h1>{title}</h1>
            </div>
            <div className="top-bar__right">{right}</div>
          </>
        )}
      </div>
      {children ? <div className="top-bar__content">{children}</div> : null}
    </header>
  );
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const { currentPath, pathname, navigate } = useRouter();
  const { isAuthenticated, telegramUser, user } = useAuth();
  const { state: networkState, retry: retryNetwork } = useNetworkState();
  const [cartCount, setCartCount] = React.useState(0);
  const [aggressiveBanners, setAggressiveBanners] = React.useState<Banner[]>([]);
  const [popupBanners, setPopupBanners] = React.useState<Banner[]>([]);
  const [showAggressivePopup, setShowAggressivePopup] = React.useState(false);
  const [showPopup, setShowPopup] = React.useState(false);
  const previousNetworkState = React.useRef(networkState);

  React.useEffect(() => {
    const previous = previousNetworkState.current;
    previousNetworkState.current = networkState;
    if ((previous === 'offline' || previous === 'recovering') && networkState === 'online') {
      window.dispatchEvent(new Event('miniapp:network-restored'));
    }
  }, [networkState]);

  React.useEffect(() => {
    let startX = 0;
    let startY = 0;
    let touchTarget: EventTarget | null = null;
    let blurredForGesture = false;

    const isTextEntryElement = (element: Element | null): element is HTMLElement => {
      if (!element) {
        return false;
      }

      return element.matches(
        'textarea, [contenteditable="true"], input:not([type="button"]):not([type="checkbox"]):not([type="radio"]):not([type="range"]):not([type="file"]):not([type="color"]):not([type="submit"]):not([type="reset"])',
      );
    };

    const blurActiveInput = () => {
      const activeElement = document.activeElement;
      if (isTextEntryElement(activeElement)) {
        activeElement.blur();
      }
    };

    const onTouchStart = (event: TouchEvent) => {
      const touch = event.touches[0];
      if (!touch || event.touches.length !== 1) {
        touchTarget = null;
        return;
      }

      startX = touch.clientX;
      startY = touch.clientY;
      touchTarget = event.target;
      blurredForGesture = false;
    };

    const onTouchMove = (event: TouchEvent) => {
      const touch = event.touches[0];
      if (!touch || event.touches.length !== 1 || blurredForGesture) {
        return;
      }

      const deltaX = Math.abs(touch.clientX - startX);
      const deltaY = Math.abs(touch.clientY - startY);
      const target = touchTarget instanceof Element ? touchTarget : null;
      const keepFocus = target?.closest('[data-keyboard-keep-focus], [role="listbox"]');

      if (!keepFocus && deltaY > 12 && deltaY > deltaX * 1.15) {
        blurActiveInput();
        blurredForGesture = true;
      }
    };

    const onWheel = (event: WheelEvent) => {
      if (Math.abs(event.deltaY) > Math.abs(event.deltaX) && Math.abs(event.deltaY) > 2) {
        blurActiveInput();
      }
    };

    document.addEventListener('touchstart', onTouchStart, { passive: true });
    document.addEventListener('touchmove', onTouchMove, { passive: true });
    document.addEventListener('wheel', onWheel, { passive: true });

    return () => {
      document.removeEventListener('touchstart', onTouchStart);
      document.removeEventListener('touchmove', onTouchMove);
      document.removeEventListener('wheel', onWheel);
    };
  }, []);

  React.useEffect(() => {
    let cancelled = false;

    async function loadCartCount() {
      if (!isAuthenticated) {
        setCartCount(0);
        return;
      }

      try {
        const cart = await getCart();
        if (!cancelled) {
          setCartCount(cart.quantity_total);
        }
      } catch {
        if (!cancelled) {
          setCartCount(0);
        }
      }
    }

    void loadCartCount();
    const onCartUpdated = () => void loadCartCount();
    window.addEventListener('miniapp:cart-updated', onCartUpdated);
    return () => {
      cancelled = true;
      window.removeEventListener('miniapp:cart-updated', onCartUpdated);
    };
  }, [isAuthenticated]);

  React.useEffect(() => {
    let cancelled = false;

    async function loadBannerPopups() {
      try {
        const result = await getBanners();
        if (cancelled) {
          return;
        }

        const entryBanners = result.items.filter((banner) => banner.display_type === 'aggressive_popup');
        const modalBanners = result.items.filter((banner) => banner.display_type === 'popup');
        if (
          window.sessionStorage.getItem(AGGRESSIVE_POPUP_SESSION_KEY) !== '1'
          && entryBanners.length > 0
        ) {
          setAggressiveBanners(entryBanners);
          setShowAggressivePopup(true);
        }
        if (window.sessionStorage.getItem(POPUP_SESSION_KEY) !== '1' && modalBanners.length > 0) {
          setPopupBanners(modalBanners);
          setShowPopup(true);
        }
      } catch {
        if (!cancelled) {
          setAggressiveBanners([]);
          setPopupBanners([]);
          setShowAggressivePopup(false);
          setShowPopup(false);
        }
      }
    }

    void loadBannerPopups();
    return () => {
      cancelled = true;
    };
  }, []);

  function closeAggressivePopup() {
    window.sessionStorage.setItem(AGGRESSIVE_POPUP_SESSION_KEY, '1');
    setShowAggressivePopup(false);
  }

  function closePopup() {
    window.sessionStorage.setItem(POPUP_SESSION_KEY, '1');
    setShowPopup(false);
  }

  const profilePhoto = telegramUser?.photo_url;
  const profileLabel = getUserDisplayName(user ?? telegramUser);

  return (
    <div className="mini-app-frame">
      <NetworkBanner state={networkState} onRetry={retryNetwork} />
      <main className="app-content">{children}</main>
      <FloatingOrderHelp currentPath={currentPath} onOpen={() => navigate('/faq?topic=order')} />
      {showAggressivePopup && aggressiveBanners.length > 0 ? (
        <BannerPopup
          banners={aggressiveBanners}
          variant="aggressive"
          onClose={closeAggressivePopup}
          onNavigate={(to) => {
            closeAggressivePopup();
            navigate(to);
          }}
        />
      ) : null}
      {!showAggressivePopup && showPopup && popupBanners.length > 0 ? (
        <BannerPopup
          banners={popupBanners}
          variant="popup"
          onClose={closePopup}
          onNavigate={(to) => {
            closePopup();
            navigate(to);
          }}
        />
      ) : null}
      <nav className="bottom-nav" aria-label="Основная навигация">
        {navItems.map((item) => {
          const active = isActive(pathname, item);
          const isCart = item.label === 'Корзина';
          const isProfile = item.label === 'Профиль';

          return (
            <Link className={`bottom-nav__item ${active ? 'is-active' : ''}`} to={item.to} key={item.to}>
              <span className="bottom-nav__icon" aria-hidden="true">
                {isProfile && profilePhoto ? (
                  <img src={profilePhoto} alt="" />
                ) : (
                  <NavIcon name={item.icon} />
                )}
                {isCart && cartCount > 0 ? <span className="cart-badge">{cartCount > 99 ? '99+' : cartCount}</span> : null}
              </span>
              <span>{item.label}</span>
              {isProfile ? <span className="sr-only">{profileLabel}</span> : null}
            </Link>
          );
        })}
      </nav>
    </div>
  );
}

function FloatingOrderHelp({
  currentPath,
  onOpen,
}: {
  currentPath: string;
  onOpen: () => void;
}) {
  const {
    hiddenSide,
    isDragging,
    isReady,
    onPointerDown,
    position,
    ref,
    restore,
    shouldSuppressClick,
    tabStyle,
  } = useDraggableFloatingHelp();

  if (!shouldShowFloatingHelp(currentPath)) {
    return null;
  }

  if (hiddenSide) {
    return (
      <button
        className={`floating-help-tab floating-help-tab--${hiddenSide}`}
        style={tabStyle}
        type="button"
        aria-label="Вернуть подсказку"
        onClick={() => restore(hiddenSide)}
      >
        <span className="floating-help-tab__chevron" aria-hidden="true" />
      </button>
    );
  }

  return (
    <button
      className={`floating-help-widget ${isReady ? 'is-ready' : ''} ${isDragging ? 'is-dragging' : ''}`}
      ref={ref}
      style={{ transform: `translate3d(${position.x}px, ${position.y}px, 0)` }}
      type="button"
      onClick={(event) => {
        if (shouldSuppressClick()) {
          event.preventDefault();
          event.stopPropagation();
          return;
        }
        onOpen();
      }}
      onPointerDown={onPointerDown}
    >
      <span aria-hidden="true">?</span>
      <strong>Как совершить заказ?</strong>
    </button>
  );
}

function useDraggableFloatingHelp() {
  const ref = React.useRef<HTMLButtonElement | null>(null);
  const cleanupRef = React.useRef<(() => void) | null>(null);
  const dragFrameRef = React.useRef<number | null>(null);
  const pendingDragStateRef = React.useRef<FloatingHelpState | null>(null);
  const suppressNextClickRef = React.useRef(false);
  const [state, setState] = React.useState<FloatingHelpState>(() => readFloatingHelpState());
  const stateRef = React.useRef(state);
  const [isReady, setIsReady] = React.useState(false);
  const [isDragging, setIsDragging] = React.useState(false);

  const setFloatingState = React.useCallback((nextState: FloatingHelpState, persist = true) => {
    stateRef.current = nextState;
    setState(nextState);
    if (persist) {
      writeFloatingHelpState(nextState);
    }
  }, []);

  const cancelDragFrame = React.useCallback(() => {
    if (dragFrameRef.current !== null) {
      if (typeof window.cancelAnimationFrame === 'function') {
        window.cancelAnimationFrame(dragFrameRef.current);
      } else {
        window.clearTimeout(dragFrameRef.current);
      }
      dragFrameRef.current = null;
    }
    pendingDragStateRef.current = null;
  }, []);

  const scheduleDragState = React.useCallback((nextState: FloatingHelpState) => {
    stateRef.current = nextState;
    pendingDragStateRef.current = nextState;
    if (dragFrameRef.current !== null) {
      return;
    }

    const flushDragState = () => {
      dragFrameRef.current = null;
      const pendingState = pendingDragStateRef.current;
      pendingDragStateRef.current = null;
      if (pendingState) {
        setState(pendingState);
      }
    };

    dragFrameRef.current = typeof window.requestAnimationFrame === 'function'
      ? window.requestAnimationFrame(flushDragState)
      : window.setTimeout(flushDragState, 16);
  }, []);

  React.useEffect(() => {
    stateRef.current = state;
  }, [state]);

  React.useLayoutEffect(() => {
    const element = ref.current;
    const currentPosition = stateRef.current.position ?? getDefaultFloatingHelpPosition(element);
    const nextPosition = clampFloatingHelpPosition(currentPosition, element);
    const nextState = {
      ...stateRef.current,
      position: nextPosition,
    };

    setFloatingState(nextState);
    setIsReady(true);
  }, [setFloatingState, state.hiddenSide]);

  React.useEffect(() => {
    function handleResize() {
      const element = ref.current;
      const currentState = stateRef.current;
      const currentPosition = currentState.position ?? getDefaultFloatingHelpPosition(element);
      setFloatingState({
        ...currentState,
        position: clampFloatingHelpPosition(currentPosition, element),
      });
    }

    window.addEventListener('resize', handleResize);
    window.visualViewport?.addEventListener('resize', handleResize);
    return () => {
      window.removeEventListener('resize', handleResize);
      window.visualViewport?.removeEventListener('resize', handleResize);
    };
  }, [setFloatingState]);

  React.useEffect(() => () => {
    cleanupRef.current?.();
    cleanupRef.current = null;
    cancelDragFrame();
  }, [cancelDragFrame]);

  const onPointerDown = React.useCallback((event: React.PointerEvent<HTMLButtonElement>) => {
    if (event.button !== 0) {
      return;
    }

    const element = ref.current;
    const startPosition = stateRef.current.position ?? getDefaultFloatingHelpPosition(element);
    const startX = event.clientX;
    const startY = event.clientY;
    const startTime = performance.now();
    const dragState = {
      lastPosition: startPosition,
      moved: false,
    };
    const offsetX = startX - startPosition.x;
    const offsetY = startY - startPosition.y;
    const pointerId = event.pointerId;
    const pointerTarget = event.currentTarget;

    cleanupRef.current?.();
    cancelDragFrame();
    pointerTarget.setPointerCapture?.(pointerId);

    const onPointerMove = (moveEvent: PointerEvent) => {
      if (moveEvent.pointerId !== pointerId) {
        return;
      }

      const deltaX = moveEvent.clientX - startX;
      const deltaY = moveEvent.clientY - startY;
      if (!dragState.moved && Math.hypot(deltaX, deltaY) <= FLOATING_HELP_DRAG_THRESHOLD) {
        return;
      }
      if (!dragState.moved) {
        dragState.moved = true;
        setIsDragging(true);
        pointerTarget.classList.add('is-dragging');
      }

      const nextPosition = clampFloatingHelpPosition(
        {
          x: moveEvent.clientX - offsetX,
          y: moveEvent.clientY - offsetY,
        },
        element,
      );

      dragState.lastPosition = nextPosition;
      const nextState = {
        hiddenSide: null,
        position: nextPosition,
      };
      scheduleDragState(nextState);
      moveEvent.preventDefault();
    };

    const finishDrag = (upEvent: PointerEvent) => {
      if (upEvent.pointerId !== pointerId) {
        return;
      }

      cleanupRef.current?.();
      cleanupRef.current = null;
      cancelDragFrame();
      setIsDragging(false);
      pointerTarget.classList.remove('is-dragging');
      pointerTarget.releasePointerCapture?.(pointerId);

      if (!dragState.moved) {
        return;
      }

      const elapsedMs = performance.now() - startTime;
      const deltaX = upEvent.clientX - startX;
      const finalPosition = clampFloatingHelpPosition(dragState.lastPosition, element);
      const dismissSide = getFloatingHelpDismissSide({
        bounds: getFloatingHelpBounds(element),
        deltaX,
        elapsedMs,
        position: finalPosition,
      });

      if (dragState.moved) {
        suppressNextClickRef.current = true;
        window.setTimeout(() => {
          suppressNextClickRef.current = false;
        }, 0);
      }

      setFloatingState({
        hiddenSide: dismissSide,
        position: finalPosition,
      });
    };

    window.addEventListener('pointermove', onPointerMove, { passive: false });
    window.addEventListener('pointerup', finishDrag);
    window.addEventListener('pointercancel', finishDrag);
    cleanupRef.current = () => {
      window.removeEventListener('pointermove', onPointerMove);
      window.removeEventListener('pointerup', finishDrag);
      window.removeEventListener('pointercancel', finishDrag);
      pointerTarget.classList.remove('is-dragging');
      cancelDragFrame();
    };
  }, [cancelDragFrame, scheduleDragState, setFloatingState]);

  const restore = React.useCallback((side: FloatingHelpHiddenSide) => {
    const bounds = getFloatingHelpBounds(null);
    const currentPosition = stateRef.current.position ?? getDefaultFloatingHelpPosition(null);
    const nextPosition = clampFloatingHelpPosition(
      {
        x: side === 'left' ? bounds.minX : bounds.maxX,
        y: currentPosition.y,
      },
      null,
    );

    setFloatingState({
      hiddenSide: null,
      position: nextPosition,
    });
  }, [setFloatingState]);

  const shouldSuppressClick = React.useCallback(() => {
    if (!suppressNextClickRef.current) {
      return false;
    }
    suppressNextClickRef.current = false;
    return true;
  }, []);

  const tabBounds = getFloatingHelpBounds(null, FLOATING_HELP_TAB_SIZE);
  const tabY = clampNumber(
    state.position?.y ?? tabBounds.maxY,
    tabBounds.minY,
    tabBounds.maxY,
  );
  const tabFrameRect = getMiniAppFrameRect(null);
  const tabViewport = getViewportRect();
  const tabX = state.hiddenSide === 'right'
    ? tabFrameRect.right - FLOATING_HELP_TAB_SIZE.width
    : tabFrameRect.left;
  const tabStyle = {
    top: `${tabY}px`,
    left: `${clampNumber(tabX, tabViewport.left, tabViewport.right - FLOATING_HELP_TAB_SIZE.width)}px`,
  } satisfies React.CSSProperties;

  return {
    hiddenSide: state.hiddenSide,
    isDragging,
    isReady,
    onPointerDown,
    position: state.position ?? getDefaultFloatingHelpPosition(ref.current),
    ref,
    restore,
    shouldSuppressClick,
    tabStyle,
  };
}

function BannerPopup({
  banners,
  variant,
  onClose,
  onNavigate,
}: {
  banners: Banner[];
  variant: 'aggressive' | 'popup';
  onClose: () => void;
  onNavigate: (to: string) => void;
}) {
  const trackRef = React.useRef<HTMLDivElement | null>(null);
  const [activeIndex, setActiveIndex] = React.useState(0);
  const interactionPauseUntil = React.useRef(0);
  const activeBanner = banners[activeIndex] ?? banners[0];
  const bannerAction = getBannerAction(activeBanner);
  const ctaLabel = getBannerCtaLabel(bannerAction);
  const hasMultipleBanners = banners.length > 1;
  const [copyNotice, setCopyNotice] = React.useState<string | null>(null);

  const updateActiveIndex = React.useCallback(() => {
    const track = trackRef.current;
    if (!track) {
      return;
    }

    const nextIndex = Math.round(track.scrollLeft / Math.max(track.clientWidth, 1));
    setActiveIndex(Math.min(Math.max(nextIndex, 0), banners.length - 1));
  }, [banners.length]);

  React.useEffect(() => {
    if (!hasMultipleBanners) {
      return undefined;
    }

    const timer = window.setInterval(() => {
      if (Date.now() < interactionPauseUntil.current) {
        return;
      }

      const track = trackRef.current;
      if (!track) {
        return;
      }

      const nextIndex = (activeIndex + 1) % banners.length;
      track.scrollTo({ left: track.clientWidth * nextIndex, behavior: getMotionAwareScrollBehavior() });
      setActiveIndex(nextIndex);
    }, 4200);

    return () => window.clearInterval(timer);
  }, [activeIndex, banners.length, hasMultipleBanners]);

  function pauseAutoplay() {
    interactionPauseUntil.current = Date.now() + 7000;
  }

  function chooseSlide(index: number) {
    const track = trackRef.current;
    pauseAutoplay();
    track?.scrollTo({ left: track.clientWidth * index, behavior: getMotionAwareScrollBehavior() });
    setActiveIndex(index);
  }

  async function handleBannerAction() {
    if (!bannerAction) {
      return;
    }

    void trackBannerClick(activeBanner.id).catch(() => undefined);

    if (bannerAction.kind === 'copy') {
      try {
        await copyTextToClipboard(bannerAction.value);
        setCopyNotice(`Промокод ${bannerAction.value} скопирован`);
      } catch {
        setCopyNotice('Не удалось скопировать промокод');
      }
      return;
    }

    if (bannerAction.kind === 'internal') {
      onNavigate(bannerAction.value);
      return;
    }

    onClose();
    window.open(bannerAction.value, '_blank', 'noopener,noreferrer');
  }

  return (
    <div
      className={`aggressive-popup aggressive-popup--${variant}`}
      role="dialog"
      aria-modal="true"
      aria-label="Акция"
    >
      <div className="aggressive-popup__backdrop" onClick={onClose} />
      <section className="aggressive-popup__card">
        <button className="aggressive-popup__close" type="button" aria-label="Закрыть" onClick={onClose}>
          ×
        </button>
        <div className="aggressive-popup__media" onPointerDown={pauseAutoplay}>
          <div className="aggressive-popup__track" ref={trackRef} onScroll={updateActiveIndex}>
            {banners.map((banner) => {
              const imageUrl = normalizeAssetUrl(banner.image_url || banner.image_path);
              return (
                <div className="aggressive-popup__slide" key={banner.id}>
                  {imageUrl ? <img src={imageUrl} alt="" /> : <span className="banner-image-fallback" />}
                </div>
              );
            })}
          </div>
        </div>
        {hasMultipleBanners ? (
          <div className="banner-dots banner-dots--popup" aria-label="Баннеры">
            {banners.map((banner, index) => (
              <button
                className={activeIndex === index ? 'is-active' : ''}
                key={banner.id}
                type="button"
                aria-label={`Баннер ${index + 1}`}
                onClick={() => chooseSlide(index)}
              />
            ))}
          </div>
        ) : null}
        {copyNotice ? <div className="banner-copy-toast">{copyNotice}</div> : null}
        {ctaLabel ? (
          <button className="banner-popup-cta" type="button" onClick={() => void handleBannerAction()}>
            {ctaLabel}
          </button>
        ) : null}
      </section>
    </div>
  );
}

function NavIcon({ name }: { name: (typeof navItems)[number]['icon'] }) {
  if (name === 'home') {
    return (
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <path d="M3.5 10.2 12 3l8.5 7.2v8.1a2.2 2.2 0 0 1-2.2 2.2H5.7a2.2 2.2 0 0 1-2.2-2.2v-8.1Z" />
        <path d="M7.2 11h1.7M11.2 11h5.6M7.2 14.5h1.7M11.2 14.5h5.6M8.2 18h7.6" />
      </svg>
    );
  }

  if (name === 'grid') {
    return (
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <rect x="3.5" y="3.5" width="17" height="17" rx="4" />
        <rect x="7" y="7" width="3" height="3" rx=".6" />
        <rect x="14" y="7" width="3" height="3" rx=".6" />
        <rect x="7" y="14" width="3" height="3" rx=".6" />
        <rect x="14" y="14" width="3" height="3" rx=".6" />
      </svg>
    );
  }

  if (name === 'search') {
    return (
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <circle cx="10.5" cy="10.5" r="6.4" />
        <path d="m15.3 15.3 4.5 4.5" />
      </svg>
    );
  }

  if (name === 'cart') {
    return (
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <path d="M3.2 4h2.6l2 10.1a2 2 0 0 0 2 1.6h6.7a2 2 0 0 0 1.9-1.5L20.7 7H6.4" />
        <circle cx="10" cy="19.3" r="1.2" />
        <circle cx="17" cy="19.3" r="1.2" />
      </svg>
    );
  }

  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <circle cx="12" cy="8.2" r="4" />
      <path d="M4.8 20c.4-4 3.1-6.3 7.2-6.3s6.8 2.3 7.2 6.3" />
    </svg>
  );
}
