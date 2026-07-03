import { cleanup, render, screen } from '@testing-library/react';
import React from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { getLooks } from '../shared/api';
import { LooksPage } from './LooksPage';

const routerMocks = vi.hoisted(() => ({
  navigate: vi.fn(),
  route: {
    currentPath: '/looks',
    pathname: '/looks',
    searchParams: new URLSearchParams(),
  },
}));

vi.mock('../shared/router/RouterProvider', () => ({
  isFirstLevelRoutePath: () => false,
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
      available_clothing_sizes: ['M', 'L'],
      available_footwear_sizes: [],
      requires_clothing_size: true,
      requires_footwear_size: false,
    }],
    meta: { limit: 60, offset: 0, total: 1 },
  }),
  toApiErrorMessage: (error: unknown) => error instanceof Error ? error.message : String(error),
}));

describe('LooksPage', () => {
  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it('renders public Look cards and links to detail route', async () => {
    render(<LooksPage />);

    expect(await screen.findByText('Summer Look')).toBeTruthy();
    expect(screen.getByText('Образ')).toBeTruthy();
    expect(getLooks).toHaveBeenCalledWith({ limit: 60, offset: 0 }, { dedupe: false });
    expect(screen.getByText('Summer Look').closest('a')?.getAttribute('href')).toBe(
      '/looks/summer-look?returnTo=%2Flooks',
    );
  });
});
