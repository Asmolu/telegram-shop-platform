import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import React from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { App } from './App';

const testState = vi.hoisted(() => ({
  networkMountCount: 0,
  resolveCategories: null as null | (() => void),
}));

const createPageMock = vi.hoisted(() => (exportName: string, label: string) => async () => {
  const ReactModule = await import('react');
  return {
    [exportName]: () => ReactModule.createElement('div', null, label),
  };
});

vi.mock('./shared/theme/ThemeProvider', async () => {
  const ReactModule = await import('react');
  return {
    ThemeProvider: ({ children }: { children: React.ReactNode }) => ReactModule.createElement(ReactModule.Fragment, null, children),
    useTheme: () => ({ theme: 'light', themePreference: 'auto', setTheme: vi.fn() }),
  };
});

vi.mock('./shared/auth/AuthProvider', async () => {
  const ReactModule = await import('react');
  return {
    AuthProvider: ({ children }: { children: React.ReactNode }) => ReactModule.createElement(ReactModule.Fragment, null, children),
    useAuth: () => ({
      status: 'development',
      user: null,
      telegramUser: null,
      error: null,
      isAuthenticated: false,
      isTelegram: false,
      loginWithToken: vi.fn(),
      clearToken: vi.fn(),
      retryTelegramAuth: vi.fn(),
    }),
  };
});

vi.mock('./shared/network/NetworkProvider', async () => {
  const ReactModule = await import('react');
  return {
    NetworkProvider: ({ children }: { children: React.ReactNode }) => {
      ReactModule.useEffect(() => {
        testState.networkMountCount += 1;
      }, []);
      return ReactModule.createElement('div', { 'data-testid': 'network-provider' }, children);
    },
    useNetworkState: () => ({ state: 'online', retry: vi.fn() }),
    useNetworkRetry: vi.fn(),
  };
});

vi.mock('./shared/api', () => ({
  getBanners: vi.fn().mockResolvedValue({ items: [], meta: { limit: 20, offset: 0, total: 0 } }),
  getCart: vi.fn().mockResolvedValue({ quantity_total: 0 }),
  trackBannerClick: vi.fn().mockResolvedValue(undefined),
}));

vi.mock('./pages/LaunchPage', createPageMock('LaunchPage', 'Launch route loaded'));
vi.mock('./pages/MainPage', createPageMock('MainPage', 'Main route loaded'));
vi.mock('./pages/CategoryPage', createPageMock('CategoryPage', 'Category detail route loaded'));
vi.mock('./pages/SearchPage', createPageMock('SearchPage', 'Search route loaded'));
vi.mock('./pages/SearchResultsPage', createPageMock('SearchResultsPage', 'Search results route loaded'));
vi.mock('./pages/ProductDetailPage', createPageMock('ProductDetailPage', 'Product route loaded'));
vi.mock('./pages/CartPage', createPageMock('CartPage', 'Cart route loaded'));
vi.mock('./pages/CheckoutPage', createPageMock('CheckoutPage', 'Checkout route loaded'));
vi.mock('./pages/OrderSuccessPage', createPageMock('OrderSuccessPage', 'Order success route loaded'));
vi.mock('./pages/PaymentPage', createPageMock('PaymentPage', 'Payment route loaded'));
vi.mock('./pages/ProfilePage', createPageMock('ProfilePage', 'Profile route loaded'));
vi.mock('./pages/PersonalDataPage', createPageMock('PersonalDataPage', 'Personal data route loaded'));
vi.mock('./pages/FaqPage', createPageMock('FaqPage', 'FAQ route loaded'));
vi.mock('./pages/NotFoundPage', createPageMock('NotFoundPage', 'Not found route loaded'));

vi.mock('./pages/CategoriesPage', () => new Promise((resolve) => {
  testState.resolveCategories = async () => {
    const ReactModule = await import('react');
    resolve({
      CategoriesPage: () => ReactModule.createElement('div', null, 'Categories route loaded'),
    });
  };
}));

describe('App lazy routes', () => {
  beforeEach(() => {
    testState.networkMountCount = 0;
    testState.resolveCategories = null;
    vi.spyOn(window, 'scrollTo').mockImplementation(() => undefined);
    window.history.replaceState(null, '', '/categories');
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it('shows a route fallback, loads the lazy route, and keeps NetworkProvider mounted across transitions', async () => {
    const { container } = render(<App />);

    expect(screen.getByRole('status').textContent).toContain('Категории');
    expect(screen.queryByText('Categories route loaded')).toBeNull();

    await waitFor(() => expect(testState.resolveCategories).not.toBeNull());
    await act(async () => {
      await testState.resolveCategories?.();
    });
    expect(await screen.findByText('Categories route loaded')).toBeTruthy();
    await waitFor(() => expect(testState.networkMountCount).toBe(1));

    const profileLink = container.querySelector<HTMLAnchorElement>('a[href="/profile"]');
    expect(profileLink).not.toBeNull();
    fireEvent.click(profileLink!);

    expect(await screen.findByText('Profile route loaded')).toBeTruthy();
    expect(testState.networkMountCount).toBe(1);
  });

  it('loads product detail for category slug product links', async () => {
    window.history.replaceState(
      null,
      '',
      '/category/futbolki/product/line-break-hoodie?sku=00001',
    );

    render(<App />);

    expect(await screen.findByText('Product route loaded')).toBeTruthy();
    expect(screen.queryByText('Category detail route loaded')).toBeNull();
  });
});
