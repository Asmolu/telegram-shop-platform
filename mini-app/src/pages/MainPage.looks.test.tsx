import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import React from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { getFeed } from '../shared/api';
import { MainPage } from './MainPage';

const routerMocks = vi.hoisted(() => ({
  navigate: vi.fn(),
  route: {
    currentPath: '/main',
    pathname: '/main',
    searchParams: new URLSearchParams(),
  },
}));

const apiMocks = vi.hoisted(() => ({
  getBanners: vi.fn(),
  getFavorites: vi.fn(),
  getFeed: vi.fn(),
  trackBannerClick: vi.fn(),
}));

vi.mock('../shared/auth/AuthProvider', () => ({
  useAuth: () => ({ isAuthenticated: false }),
}));

vi.mock('../shared/telemetry', () => ({
  trackTelemetry: vi.fn(),
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
    <a
      href={to}
      onClick={(event) => {
        event.preventDefault();
        routerMocks.navigate(to);
      }}
      {...props}
    >
      {children}
    </a>
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
  getBanners: apiMocks.getBanners,
  getFavorites: apiMocks.getFavorites,
  getFeed: apiMocks.getFeed,
  toApiErrorMessage: (error: unknown) => error instanceof Error ? error.message : String(error),
  trackBannerClick: apiMocks.trackBannerClick,
}));

describe('MainPage mixed feed', () => {
  beforeEach(() => {
    apiMocks.getBanners.mockResolvedValue({
      items: [],
      meta: { limit: 20, offset: 0, total: 0 },
    });
    apiMocks.getFavorites.mockResolvedValue({ items: [] });
    apiMocks.getFeed.mockResolvedValue(mixedFeedFixture());
  });

  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it('calls the mixed feed endpoint and renders products and Looks in the same grid', async () => {
    const { container } = render(<MainPage />);

    expect(await screen.findByText('Line Break Hoodie')).toBeTruthy();
    expect(screen.getByText('Summer Look')).toBeTruthy();
    expect(screen.getByText('Образ')).toBeTruthy();
    expect(container.querySelectorAll('.product-grid > .product-card')).toHaveLength(2);
    expect(getFeed).toHaveBeenCalledWith({ limit: 40, offset: 0 });
  });

  it('opens product detail and Look detail from mixed cards', async () => {
    render(<MainPage />);

    fireEvent.click(await screen.findByText('Line Break Hoodie'));
    fireEvent.click(screen.getByText('Summer Look'));

    expect(routerMocks.navigate).toHaveBeenCalledWith('/product/10?returnTo=%2Fmain');
    expect(routerMocks.navigate).toHaveBeenCalledWith('/looks/summer-look?returnTo=%2Fmain');
  });

  it('renders an empty state when the mixed feed is empty', async () => {
    apiMocks.getFeed.mockResolvedValueOnce({
      items: [],
      meta: { limit: 40, offset: 0, total: 0 },
    });

    render(<MainPage />);

    expect(await screen.findByText('Товары скоро появятся')).toBeTruthy();
  });

  it('renders loading and error states for the mixed feed', async () => {
    let rejectFeed: (error: Error) => void = () => undefined;
    apiMocks.getFeed.mockReturnValueOnce(new Promise((_resolve, reject) => {
      rejectFeed = reject;
    }));

    const { container } = render(<MainPage />);

    expect(container.querySelector('.product-card--skeleton')).not.toBeNull();

    rejectFeed(new Error('Feed unavailable'));

    await waitFor(() => expect(screen.getByText('Feed unavailable')).toBeTruthy());
  });
});

function mixedFeedFixture() {
  return {
    items: [
      {
        type: 'product',
        product: {
          id: 10,
          name: 'Line Break Hoodie',
          slug: 'line-break-hoodie',
          brand: 'ICON STORE',
          base_price: '1000.00',
          old_price: null,
          size_grid: 'clothing_alpha',
          image_badge_type: 'none',
          image_badge_text: null,
          image_badge_color: null,
          image_badge_position: null,
          image_url: null,
          thumbnail_image_url: null,
          variants: [{
            id: 100,
            product_id: 10,
            size: 'M',
            color: null,
            available_quantity: 3,
            is_active: true,
          }],
          is_available: true,
          created_at: '2026-07-03T12:00:00Z',
        },
      },
      {
        type: 'look',
        look: {
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
        },
      },
    ],
    meta: { limit: 40, offset: 0, total: 2 },
  };
}
