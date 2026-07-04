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
    window.localStorage.clear();
  });

  it('renders the existing order help content', () => {
    render(<AppShell><div>Feed content</div></AppShell>);

    const widget = screen.getByRole('button', { name: /Как совершить заказ/i });

    expect(widget.textContent).toContain('?');
    expect(widget.textContent).toContain('Как совершить заказ?');
  });

  it('can be hidden to the left and opened from the side tab', async () => {
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

    expect(routerMocks.navigate).toHaveBeenCalledWith('/faq?topic=order&returnTo=%2Fmain');
  });

  it('can be hidden to the right and opened from the side tab', async () => {
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

    const stored = JSON.parse(window.localStorage.getItem('telegram_shop_order_help_widget_v1') ?? '{}');
    expect(stored.hiddenSide).toBe('left');
    expect(stored.position.y).toBeLessThan(640);
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
