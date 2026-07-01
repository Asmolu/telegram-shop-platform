import { cleanup, fireEvent, render, screen } from '@testing-library/react';
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
    vi.clearAllMocks();
    window.localStorage.clear();
  });

  it('renders the existing order help content', () => {
    render(<AppShell><div>Feed content</div></AppShell>);

    const widget = screen.getByRole('button', { name: /Как совершить заказ/i });

    expect(widget.textContent).toContain('?');
    expect(widget.textContent).toContain('Как совершить заказ?');
  });

  it('can be hidden to the left and restored from the side tab', () => {
    render(<AppShell><div>Feed content</div></AppShell>);

    const widget = screen.getByRole('button', { name: /Как совершить заказ/i });
    dispatchPointer(widget, 'pointerdown', { button: 0, clientX: 260, clientY: 690, pointerId: 1 });
    dispatchPointer(window, 'pointermove', { clientX: 50, clientY: 690, pointerId: 1 });
    dispatchPointer(window, 'pointerup', { clientX: 30, clientY: 690, pointerId: 1 });

    expect(screen.queryByRole('button', { name: /Как совершить заказ/i })).toBeNull();
    const tab = document.querySelector<HTMLButtonElement>('.floating-help-tab--left');

    expect(tab).not.toBeNull();
    expect(tab?.textContent).toBe('');
    expect(tab?.querySelector('.floating-help-tab__chevron')).not.toBeNull();
    fireEvent.click(tab!);

    expect(screen.getByRole('button', { name: /Как совершить заказ/i })).toBeTruthy();
  });

  it('can be hidden to the right and restored from the side tab', () => {
    render(<AppShell><div>Search content</div></AppShell>);

    const widget = screen.getByRole('button', { name: /Как совершить заказ/i });
    dispatchPointer(widget, 'pointerdown', { button: 0, clientX: 260, clientY: 690, pointerId: 2 });
    dispatchPointer(window, 'pointermove', { clientX: 380, clientY: 690, pointerId: 2 });
    dispatchPointer(window, 'pointerup', { clientX: 390, clientY: 690, pointerId: 2 });

    expect(screen.queryByRole('button', { name: /Как совершить заказ/i })).toBeNull();
    const tab = document.querySelector<HTMLButtonElement>('.floating-help-tab--right');

    expect(tab).not.toBeNull();
    expect(tab?.textContent).toBe('');
    expect(tab?.querySelector('.floating-help-tab__chevron')).not.toBeNull();
    fireEvent.click(tab!);

    expect(screen.getByRole('button', { name: /Как совершить заказ/i })).toBeTruthy();
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
