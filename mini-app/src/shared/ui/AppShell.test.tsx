import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import React from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { AppShell } from './AppShell';

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
  Link: ({ children, to, ...props }: React.PropsWithChildren<{ to: string }>) => (
    <a href={to} {...props}>{children}</a>
  ),
  useRouter: () => ({
    currentPath: routerMocks.currentPath,
    goBack: routerMocks.goBack,
    navigate: routerMocks.navigate,
    pathname: routerMocks.pathname,
  }),
}));

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
    const tab = screen.getByText('>');

    fireEvent.click(tab);

    expect(screen.getByRole('button', { name: /Как совершить заказ/i })).toBeTruthy();
  });

  it('can be hidden to the right and restored from the side tab', () => {
    render(<AppShell><div>Search content</div></AppShell>);

    const widget = screen.getByRole('button', { name: /Как совершить заказ/i });
    dispatchPointer(widget, 'pointerdown', { button: 0, clientX: 260, clientY: 690, pointerId: 2 });
    dispatchPointer(window, 'pointermove', { clientX: 380, clientY: 690, pointerId: 2 });
    dispatchPointer(window, 'pointerup', { clientX: 390, clientY: 690, pointerId: 2 });

    expect(screen.queryByRole('button', { name: /Как совершить заказ/i })).toBeNull();
    const tab = screen.getByText('<');

    fireEvent.click(tab);

    expect(screen.getByRole('button', { name: /Как совершить заказ/i })).toBeTruthy();
  });
});
