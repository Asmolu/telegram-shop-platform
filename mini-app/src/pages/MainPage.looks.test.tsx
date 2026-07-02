import { cleanup, render, screen, waitFor } from '@testing-library/react';
import React from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { getLooks, getProducts } from '../shared/api';
import { MainPage } from './MainPage';

const routerMocks = vi.hoisted(() => ({
  navigate: vi.fn(),
  route: {
    currentPath: '/main',
    pathname: '/main',
    searchParams: new URLSearchParams(),
  },
}));

vi.mock('../shared/auth/AuthProvider', () => ({
  useAuth: () => ({ isAuthenticated: false }),
}));

vi.mock('../shared/router/routePrefetch', () => ({
  scheduleRoutePrefetch: vi.fn(() => undefined),
}));

vi.mock('../features/catalog/SearchAutocomplete', () => ({
  SearchAutocomplete: ({ value, onChange, placeholder }: {
    value: string;
    onChange: (value: string) => void;
    placeholder: string;
  }) => (
    <input
      aria-label="Поиск"
      value={value}
      placeholder={placeholder}
      onChange={(event) => onChange(event.target.value)}
    />
  ),
}));

vi.mock('../features/catalog/useProductActions', () => ({
  useProductActions: () => ({
    addToCart: vi.fn(),
    clearNotice: vi.fn(),
    notice: null,
    sizePicker: null,
    toggleFavorite: vi.fn(),
  }),
}));

vi.mock('../shared/router/RouterProvider', () => ({
  isFirstLevelRoutePath: () => true,
  Link: ({ children, to, ...props }: React.PropsWithChildren<{ to: string }>) => (
    <a href={to} {...props}>{children}</a>
  ),
  useRouter: () => ({
    currentPath: routerMocks.route.currentPath,
    pathname: routerMocks.route.pathname,
    navigate: routerMocks.navigate,
    searchParams: routerMocks.route.searchParams,
    goBack: vi.fn(),
  }),
  withReturnTo: (path: string, returnTo?: string | null) => (
    returnTo ? `${path}?returnTo=${encodeURIComponent(returnTo)}` : path
  ),
}));

vi.mock('../shared/api', () => ({
  getApiBaseUrl: vi.fn(() => ''),
  getBanners: vi.fn().mockResolvedValue({ items: [], meta: { limit: 20, offset: 0, total: 0 } }),
  getFavorites: vi.fn().mockResolvedValue({ items: [] }),
  getLooks: vi.fn().mockResolvedValue({
    items: [{
      id: 1,
      slug: 'summer-look',
      title: 'Summer Look',
      description: 'Ready outfit',
      primary_image_url: '/uploads/looks/summer.webp',
      price: '1500.00',
      old_price: null,
      item_count: 2,
      is_available: true,
      available_sizes: ['M', 'L'],
    }],
    meta: { limit: 8, offset: 0, total: 1 },
  }),
  getProducts: vi.fn().mockResolvedValue({ items: [], meta: { limit: 40, offset: 0, total: 0 } }),
  toApiErrorMessage: (error: unknown) => error instanceof Error ? error.message : String(error),
  trackBannerClick: vi.fn().mockResolvedValue(undefined),
}));

describe('MainPage Looks section', () => {
  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it('renders a Looks section when public Looks are returned', async () => {
    render(<MainPage />);

    expect(await screen.findByRole('heading', { name: 'Образы' })).toBeTruthy();
    expect(screen.getByText('Summer Look')).toBeTruthy();
    expect(screen.getByText('Образ')).toBeTruthy();
    const lookLink = screen.getByText('Summer Look').closest('a');

    expect(getProducts).toHaveBeenCalledWith({ limit: 40, offset: 0, status: 'ACTIVE' });
    expect(getLooks).toHaveBeenCalledWith({ limit: 8, offset: 0 });
    expect(lookLink?.getAttribute('href')).toBe('/looks/summer-look?returnTo=%2Fmain');
  });

  it('keeps the product feed usable if Looks fail to load', async () => {
    vi.mocked(getLooks).mockRejectedValueOnce(new Error('Looks unavailable'));

    render(<MainPage />);

    await waitFor(() => expect(getProducts).toHaveBeenCalled());
    expect(screen.queryByText('Summer Look')).toBeNull();
    expect(screen.getByText('Товары скоро появятся')).toBeTruthy();
  });
});
