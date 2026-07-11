import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import React from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { AppShell, TopBar } from './AppShell';

const routerMocks = vi.hoisted(() => ({
  currentPath: '/main',
  goBack: vi.fn(),
  navigate: vi.fn(),
  pathname: '/main',
}));

vi.mock('../api', () => ({
  getBanners: vi.fn().mockResolvedValue({ items: [], meta: { limit: 20, offset: 0, total: 0 } }),
  getCart: vi.fn().mockResolvedValue({ quantity_total: 0 }),
  trackBannerClick: vi.fn().mockResolvedValue(undefined),
}));

vi.mock('../auth/AuthProvider', () => ({
  useAuth: () => ({
    isAuthenticated: false,
    telegramUser: null,
    user: null,
  }),
}));

vi.mock('../network/NetworkBanner', () => ({
  NetworkBanner: () => null,
}));

vi.mock('../network/NetworkProvider', () => ({
  useNetworkState: () => ({ retry: vi.fn(), state: 'online' }),
}));

vi.mock('../router/RouterProvider', () => ({
  isFirstLevelRoutePath: (path: string) => {
    const url = new URL(path, window.location.origin);
    return ['/', '/main', '/categories', '/search', '/cart', '/profile'].includes(url.pathname);
  },
  Link: ({ children, to, ...props }: React.PropsWithChildren<{ to: string }>) => (
    <a href={to} {...props}>{children}</a>
  ),
  useRouter: () => ({
    currentPath: routerMocks.currentPath,
    goBack: routerMocks.goBack,
    navigate: routerMocks.navigate,
    pathname: routerMocks.pathname,
  }),
  withReturnTo: (to: string, returnTo: string) => `${to}${to.includes('?') ? '&' : '?'}returnTo=${encodeURIComponent(returnTo)}`,
}));

type TestBackButton = {
  show: ReturnType<typeof vi.fn>;
  hide: ReturnType<typeof vi.fn>;
  onClick: ReturnType<typeof vi.fn>;
  offClick: ReturnType<typeof vi.fn>;
};

function setRoute(path: string) {
  const url = new URL(path, window.location.origin);
  routerMocks.currentPath = `${url.pathname}${url.search}`;
  routerMocks.pathname = url.pathname;
}

function installTelegramBackButton(): TestBackButton {
  const backButton = {
    show: vi.fn(),
    hide: vi.fn(),
    onClick: vi.fn(),
    offClick: vi.fn(),
  };

  window.Telegram = {
    WebApp: {
      initData: '',
      BackButton: backButton,
    },
  };

  return backButton;
}

class TestPointerEvent extends MouseEvent {
  pointerId: number;

  constructor(type: string, init: PointerEventInit = {}) {
    super(type, init);
    this.pointerId = init.pointerId ?? 1;
  }
}

function dispatchPointer(target: Window | Document | Node | Element, type: string, init: PointerEventInit) {
  fireEvent(target, new TestPointerEvent(type, { bubbles: true, cancelable: true, ...init }) as PointerEvent);
}

describe('AppShell floating order help', () => {
  beforeEach(() => {
    routerMocks.currentPath = '/main';
    routerMocks.pathname = '/main';
    window.localStorage.clear();
    Object.defineProperty(window, 'innerWidth', { configurable: true, value: 390 });
    Object.defineProperty(window, 'innerHeight', { configurable: true, value: 800 });
    Object.defineProperty(HTMLElement.prototype, 'setPointerCapture', {
      configurable: true,
      value: vi.fn(),
    });
    Object.defineProperty(HTMLElement.prototype, 'releasePointerCapture', {
      configurable: true,
      value: vi.fn(),
    });
  });

  afterEach(() => {
    cleanup();
    delete window.Telegram;
    Object.defineProperty(window, 'visualViewport', { configurable: true, value: undefined });
    document.documentElement.style.removeProperty('--keyboard-inset');
    document.documentElement.classList.remove('keyboard-input-focused', 'keyboard-open');
    delete document.documentElement.dataset.keyboardOpen;
    vi.clearAllMocks();
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
    Object.defineProperty(window, 'matchMedia', { configurable: true, value: undefined });
    window.localStorage.clear();
  });

  it('renders the existing order help content', () => {
    render(<AppShell><div>Feed content</div></AppShell>);

    const widget = screen.getByRole('button', { name: /Как совершить заказ/i });

    expect(widget.textContent).toContain('?');
    expect(widget.textContent).toContain('Как совершить заказ?');
    expect(widget.classList.contains('floating-help-widget')).toBe(true);
    expect(widget.classList.contains('is-ready')).toBe(true);
  });

  it('opens the order FAQ only when the expanded widget is tapped', () => {
    render(<AppShell><div>Feed content</div></AppShell>);

    fireEvent.click(screen.getByRole('button', { name: 'Как совершить заказ?' }));

    expect(routerMocks.navigate).toHaveBeenCalledWith('/faq?topic=order&returnTo=%2Fmain');
  });

  it('supports normal two-axis dragging without navigating', () => {
    render(<AppShell><div>Feed content</div></AppShell>);

    const widget = screen.getByRole('button', { name: 'Как совершить заказ?' });
    dispatchPointer(widget, 'pointerdown', { button: 0, clientX: 260, clientY: 690, pointerId: 20 });
    dispatchPointer(window, 'pointermove', { clientX: 235, clientY: 560, pointerId: 20 });
    dispatchPointer(window, 'pointerup', { clientX: 235, clientY: 560, pointerId: 20 });
    fireEvent.click(widget);

    expect(screen.getByRole('button', { name: 'Как совершить заказ?' })).toBeTruthy();
    expect(routerMocks.navigate).not.toHaveBeenCalled();
  });

  it('can be hidden to the left and restored from the side tab before opening FAQ', async () => {
    render(<AppShell><div>Feed content</div></AppShell>);

    const widget = screen.getByRole('button', { name: /Как совершить заказ/i });
    dispatchPointer(widget, 'pointerdown', { button: 0, clientX: 260, clientY: 690, pointerId: 1 });
    dispatchPointer(window, 'pointermove', { clientX: 50, clientY: 690, pointerId: 1 });
    dispatchPointer(window, 'pointerup', { clientX: 30, clientY: 690, pointerId: 1 });

    expect(screen.queryByText('Как совершить заказ?')).toBeNull();
    const tab = document.querySelector<HTMLButtonElement>('.floating-help-tab--left');

    expect(tab).not.toBeNull();
    expect(tab?.textContent).toBe('');
    expect(tab?.querySelector('.floating-help-tab__chevron')).not.toBeNull();
    await new Promise((resolve) => window.setTimeout(resolve, 0));
    fireEvent.click(tab!);

    expect(routerMocks.navigate).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: 'Как совершить заказ?' }));
    expect(routerMocks.navigate).toHaveBeenCalledWith('/faq?topic=order&returnTo=%2Fmain');
  });

  it('can be hidden to the right and restored from the side tab before opening FAQ', async () => {
    render(<AppShell><div>Search content</div></AppShell>);

    const widget = screen.getByRole('button', { name: /Как совершить заказ/i });
    dispatchPointer(widget, 'pointerdown', { button: 0, clientX: 260, clientY: 690, pointerId: 2 });
    dispatchPointer(window, 'pointermove', { clientX: 380, clientY: 690, pointerId: 2 });
    dispatchPointer(window, 'pointerup', { clientX: 390, clientY: 690, pointerId: 2 });

    expect(screen.queryByText('Как совершить заказ?')).toBeNull();
    const tab = document.querySelector<HTMLButtonElement>('.floating-help-tab--right');

    expect(tab).not.toBeNull();
    expect(tab?.textContent).toBe('');
    expect(tab?.querySelector('.floating-help-tab__chevron')).not.toBeNull();
    await new Promise((resolve) => window.setTimeout(resolve, 0));
    fireEvent.click(tab!);

    expect(routerMocks.navigate).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: 'Как совершить заказ?' }));
    expect(routerMocks.navigate).toHaveBeenCalledWith('/faq?topic=order&returnTo=%2Fmain');
  });

  it('drags the side tab vertically, stores the position, and suppresses accidental open', () => {
    render(<AppShell><div>Feed content</div></AppShell>);

    const widget = screen.getByRole('button', { name: /Как совершить заказ/i });
    dispatchPointer(widget, 'pointerdown', { button: 0, clientX: 260, clientY: 690, pointerId: 3 });
    dispatchPointer(window, 'pointermove', { clientX: 50, clientY: 690, pointerId: 3 });
    dispatchPointer(window, 'pointerup', { clientX: 30, clientY: 690, pointerId: 3 });

    const tab = document.querySelector<HTMLButtonElement>('.floating-help-tab--left');
    expect(tab).not.toBeNull();

    dispatchPointer(tab!, 'pointerdown', { button: 0, clientX: 4, clientY: 640, pointerId: 4 });
    dispatchPointer(window, 'pointermove', { clientX: 4, clientY: 520, pointerId: 4 });
    dispatchPointer(window, 'pointerup', { clientX: 4, clientY: 520, pointerId: 4 });
    fireEvent.click(tab!);

    const stored = JSON.parse(window.localStorage.getItem('telegram_shop_order_help_widget_v2') ?? '{}');
    expect(stored.hiddenSide).toBe('left');
    expect(stored.position.y).toBeLessThan(640);
    expect(routerMocks.navigate).not.toHaveBeenCalled();
  });

  it.each([
    ['left', 4, 100],
    ['right', 386, 285],
  ] as const)('restores from the %s tab with one continuous inward drag', (side, startX, endX) => {
    window.localStorage.setItem('telegram_shop_order_help_widget_v2', JSON.stringify({
      hiddenSide: side,
      position: { x: side === 'left' ? 12 : 214, y: 560 },
    }));
    render(<AppShell><div>Feed content</div></AppShell>);

    const tab = document.querySelector<HTMLButtonElement>(`.floating-help-tab--${side}`);
    expect(tab).not.toBeNull();
    dispatchPointer(tab!, 'pointerdown', { button: 0, clientX: startX, clientY: 580, pointerId: side === 'left' ? 21 : 22 });
    dispatchPointer(window, 'pointermove', { clientX: endX, clientY: 540, pointerId: side === 'left' ? 21 : 22 });
    dispatchPointer(window, 'pointerup', { clientX: endX, clientY: 540, pointerId: side === 'left' ? 21 : 22 });

    expect(document.querySelector('.floating-help-tab')).toBeNull();
    expect(screen.getByRole('button', { name: 'Как совершить заказ?' })).toBeTruthy();
    expect(routerMocks.navigate).not.toHaveBeenCalled();
    expect(JSON.parse(window.localStorage.getItem('telegram_shop_order_help_widget_v2') ?? '{}').hiddenSide).toBeNull();
  });

  it.each(['left', 'right'] as const)('uses the inward-facing chevron class for the %s tab', (side) => {
    window.localStorage.setItem('telegram_shop_order_help_widget_v2', JSON.stringify({
      hiddenSide: side,
      position: { x: 12, y: 500 },
    }));
    render(<AppShell><div>Feed content</div></AppShell>);

    const tab = screen.getByRole('button', { name: 'Показать подсказку «Как совершить заказ?»' });
    expect(tab.classList.contains(`floating-help-tab--${side}`)).toBe(true);
    expect(tab.querySelector('.floating-help-tab__chevron')).not.toBeNull();
  });

  it('persists collapsed state only under the v2 storage key', () => {
    render(<AppShell><div>Feed content</div></AppShell>);

    const widget = screen.getByRole('button', { name: 'Как совершить заказ?' });
    dispatchPointer(widget, 'pointerdown', { button: 0, clientX: 260, clientY: 690, pointerId: 23 });
    dispatchPointer(window, 'pointermove', { clientX: 380, clientY: 690, pointerId: 23 });
    dispatchPointer(window, 'pointerup', { clientX: 390, clientY: 690, pointerId: 23 });

    expect(JSON.parse(window.localStorage.getItem('telegram_shop_order_help_widget_v2') ?? '{}').hiddenSide).toBe('right');
    expect(window.localStorage.getItem('telegram_shop_order_help_widget_v1')).toBeNull();
  });

  it('ignores old v1 hidden state so existing users see the expanded widget once', () => {
    window.localStorage.setItem('telegram_shop_order_help_widget_v1', JSON.stringify({
      hiddenSide: 'right',
      position: { x: 214, y: 600 },
    }));

    render(<AppShell><div>Feed content</div></AppShell>);

    expect(screen.getByRole('button', { name: 'Как совершить заказ?' })).toBeTruthy();
    expect(document.querySelector('.floating-help-tab')).toBeNull();
  });

  it.each(['not-json', JSON.stringify({ hiddenSide: 'left', position: { x: 'bad' } })])(
    'falls back to expanded for malformed v2 state %s',
    (storedState) => {
      window.localStorage.setItem('telegram_shop_order_help_widget_v2', storedState);
      render(<AppShell><div>Feed content</div></AppShell>);

      expect(screen.getByRole('button', { name: 'Как совершить заказ?' })).toBeTruthy();
    },
  );

  it('reclamps the expanded widget after resize and keeps it above bottom navigation', () => {
    window.localStorage.setItem('telegram_shop_order_help_widget_v2', JSON.stringify({
      hiddenSide: null,
      position: { x: 999, y: 999 },
    }));
    render(<AppShell><div>Feed content</div></AppShell>);
    const widget = screen.getByRole('button', { name: 'Как совершить заказ?' });
    const initialTransform = widget.style.transform;

    Object.defineProperty(window, 'innerWidth', { configurable: true, value: 260 });
    Object.defineProperty(window, 'innerHeight', { configurable: true, value: 500 });
    fireEvent(window, new Event('resize'));

    expect(widget.style.transform).not.toBe(initialTransform);
    const coordinates = widget.style.transform.match(/translate3d\(([-\d.]+)px, ([-\d.]+)px/);
    expect(Number(coordinates?.[1])).toBeLessThanOrEqual(84);
    expect(Number(coordinates?.[2])).toBeLessThanOrEqual(366);
  });

  it('reclamps a collapsed tab after resize', () => {
    window.localStorage.setItem('telegram_shop_order_help_widget_v2', JSON.stringify({
      hiddenSide: 'right',
      position: { x: 214, y: 650 },
    }));
    render(<AppShell><div>Feed content</div></AppShell>);
    const tab = screen.getByRole('button', { name: 'Показать подсказку «Как совершить заказ?»' });
    const initialTop = Number.parseFloat(tab.style.top);

    Object.defineProperty(window, 'innerHeight', { configurable: true, value: 420 });
    fireEvent(window, new Event('resize'));

    expect(Number.parseFloat(tab.style.top)).toBeLessThan(initialTop);
    expect(Number.parseFloat(tab.style.top)).toBeLessThanOrEqual(286);
  });

  it.each([
    '/faq',
    '/product/10',
    '/cart?tab=cart',
    '/checkout',
    '/order-success/10',
    '/orders/10/return',
    '/profile',
  ])('does not render on non-discovery route %s', (path) => {
    setRoute(path);
    render(<AppShell><div>Other content</div></AppShell>);

    expect(screen.queryByRole('button', { name: /Как совершить заказ/ })).toBeNull();
  });

  it.each(['/', '/main', '/categories', '/category/2', '/search', '/search/results?q=coat'])(
    'renders on discovery route %s',
    (path) => {
      setRoute(path);
      render(<AppShell><div>Discovery content</div></AppShell>);

      expect(screen.getByRole('button', { name: 'Как совершить заказ?' })).toBeTruthy();
    },
  );

  it('removes gesture listeners and cancels a pending animation frame on unmount', () => {
    const removeEventListener = vi.spyOn(window, 'removeEventListener');
    const cancelAnimationFrame = vi.fn();
    vi.stubGlobal('cancelAnimationFrame', cancelAnimationFrame);
    vi.stubGlobal('requestAnimationFrame', vi.fn(() => 77));
    const { unmount } = render(<AppShell><div>Feed content</div></AppShell>);
    const widget = screen.getByRole('button', { name: 'Как совершить заказ?' });
    dispatchPointer(widget, 'pointerdown', { button: 0, clientX: 260, clientY: 690, pointerId: 24 });
    dispatchPointer(window, 'pointermove', { clientX: 250, clientY: 600, pointerId: 24 });

    unmount();

    expect(removeEventListener).toHaveBeenCalledWith('pointermove', expect.any(Function));
    expect(removeEventListener).toHaveBeenCalledWith('pointerup', expect.any(Function));
    expect(removeEventListener).toHaveBeenCalledWith('pointercancel', expect.any(Function));
    expect(cancelAnimationFrame).toHaveBeenCalledWith(77);
    vi.unstubAllGlobals();
  });

  it('keeps collapse and restore functional with reduced motion requested', async () => {
    Object.defineProperty(window, 'matchMedia', {
      configurable: true,
      value: vi.fn(() => ({ matches: true, addEventListener: vi.fn(), removeEventListener: vi.fn() })),
    });
    render(<AppShell><div>Feed content</div></AppShell>);
    const widget = screen.getByRole('button', { name: 'Как совершить заказ?' });
    dispatchPointer(widget, 'pointerdown', { button: 0, clientX: 260, clientY: 690, pointerId: 25 });
    dispatchPointer(window, 'pointermove', { clientX: 50, clientY: 690, pointerId: 25 });
    dispatchPointer(window, 'pointerup', { clientX: 30, clientY: 690, pointerId: 25 });
    await new Promise((resolve) => window.setTimeout(resolve, 0));

    fireEvent.click(screen.getByRole('button', { name: 'Показать подсказку «Как совершить заказ?»' }));

    expect(screen.getByRole('button', { name: 'Как совершить заказ?' })).toBeTruthy();
    expect(routerMocks.navigate).not.toHaveBeenCalled();
  });

  it('keeps focused Mini App form inputs visible when the keyboard opens', async () => {
    const scrollTo = vi.spyOn(window, 'scrollTo').mockImplementation(() => undefined);
    Object.defineProperty(window, 'visualViewport', {
      configurable: true,
      value: {
        addEventListener: vi.fn(),
        height: 520,
        offsetLeft: 0,
        offsetTop: 0,
        removeEventListener: vi.fn(),
        width: 390,
      },
    });

    render(
      <AppShell>
        <form>
          <label>Search field<input /></label>
          <label>Checkout city<input /></label>
          <label>Profile comment<textarea /></label>
        </form>
      </AppShell>,
    );

    fireEvent.focusIn(screen.getByLabelText('Search field'));
    expect(document.documentElement.classList.contains('keyboard-open')).toBe(true);
    expect(document.documentElement.style.getPropertyValue('--keyboard-inset')).toBe('280px');
    await waitFor(() => expect(scrollTo).toHaveBeenCalled());

    fireEvent.focusIn(screen.getByLabelText('Checkout city'));
    fireEvent.focusIn(screen.getByLabelText('Profile comment'));

    expect(document.documentElement.classList.contains('keyboard-input-focused')).toBe(true);
  });
});

describe('TopBar back behavior', () => {
  beforeEach(() => {
    setRoute('/main');
  });

  afterEach(() => {
    cleanup();
    delete window.Telegram;
    vi.clearAllMocks();
  });

  it.each(['/main', '/categories', '/search', '/cart?tab=cart', '/profile'])(
    'hides the custom back button on first-level route %s',
    (path) => {
      setRoute(path);

      const { container } = render(<TopBar title="ICON STORE" />);

      expect(container.querySelector('.top-bar__back-button')).toBeNull();
    },
  );

  it('renders the custom back button on nested routes and delegates to the logical router back', () => {
    setRoute('/product/10?returnTo=%2Fsearch%2Fresults%3Fq%3Dhoodie');

    const { container } = render(<TopBar title="Product" backFallback="/main" />);
    const backButton = container.querySelector<HTMLButtonElement>('.top-bar__back-button');

    expect(backButton).not.toBeNull();
    expect(backButton?.classList.contains('top-bar__back-button--transparent')).toBe(true);
    fireEvent.click(backButton!);
    expect(routerMocks.goBack).toHaveBeenCalledWith('/main');
  });

  it('syncs Telegram BackButton visibility and click handling with route depth', () => {
    setRoute('/checkout');
    const backButton = installTelegramBackButton();

    const { unmount } = render(<TopBar title="Checkout" backFallback="/cart?tab=cart" />);

    expect(backButton.show).toHaveBeenCalledTimes(1);
    expect(backButton.onClick).toHaveBeenCalledWith(expect.any(Function));

    const nativeClick = backButton.onClick.mock.calls[0][0] as () => void;
    nativeClick();

    expect(routerMocks.goBack).toHaveBeenCalledWith('/cart?tab=cart');
    unmount();
    expect(backButton.offClick).toHaveBeenCalledWith(nativeClick);
    expect(backButton.hide).toHaveBeenCalled();
  });

  it('hides Telegram BackButton on first-level routes', () => {
    setRoute('/categories');
    const backButton = installTelegramBackButton();

    render(<TopBar title="Categories" />);

    expect(backButton.hide).toHaveBeenCalledTimes(1);
    expect(backButton.show).not.toHaveBeenCalled();
  });
});
