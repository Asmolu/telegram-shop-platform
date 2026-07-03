import { cleanup, render, waitFor } from '@testing-library/react';
import React from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { CategoryPage, getCategoryPageRoute } from './CategoryPage';

const apiMocks = vi.hoisted(() => ({
  getCategory: vi.fn(),
  getFavorites: vi.fn(),
  getProducts: vi.fn(),
  resolveCategory: vi.fn(),
}));

const routerMocks = vi.hoisted(() => ({
  navigate: vi.fn(),
  route: {
    currentPath: '/category/futbolki',
    pathname: '/category/futbolki',
  },
}));

vi.mock('../shared/api', () => ({
  ApiClientError: class ApiClientError extends Error {
    status: number;

    constructor(status = 500) {
      super('api error');
      this.status = status;
    }
  },
  getCategory: apiMocks.getCategory,
  getFavorites: apiMocks.getFavorites,
  getProducts: apiMocks.getProducts,
  resolveCategory: apiMocks.resolveCategory,
  toApiErrorMessage: (error: unknown) => error instanceof Error ? error.message : String(error),
}));

vi.mock('../shared/auth/AuthProvider', () => ({
  useAuth: () => ({ isAuthenticated: false }),
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
  getNumericRouteParam: (pathname: string, prefix: string) => {
    const raw = pathname.replace(prefix, '').split('/')[0];
    return Number(raw);
  },
  isFirstLevelRoutePath: () => false,
  useRouter: () => ({
    currentPath: routerMocks.route.currentPath,
    pathname: routerMocks.route.pathname,
    navigate: routerMocks.navigate,
    goBack: vi.fn(),
  }),
}));

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  routerMocks.route.currentPath = '/category/futbolki';
  routerMocks.route.pathname = '/category/futbolki';
  apiMocks.getProducts.mockResolvedValue({ items: [], meta: { limit: 100, offset: 0, total: 0 } });
  apiMocks.getFavorites.mockResolvedValue({ items: [] });
});

describe('getCategoryPageRoute', () => {
  it('keeps numeric category routes as id routes', () => {
    expect(getCategoryPageRoute('/category/7')).toEqual({
      mode: 'id',
      categoryId: 7,
      fallbackSlug: '7',
    });
  });

  it('supports category slug routes', () => {
    expect(getCategoryPageRoute('/category/futbolki')).toEqual({
      mode: 'slug',
      categorySlug: 'futbolki',
    });
  });

  it('opens an old category slug and replaces the route with the canonical slug', async () => {
    routerMocks.route.currentPath = '/category/old-category?source=channel';
    routerMocks.route.pathname = '/category/old-category';
    apiMocks.resolveCategory.mockResolvedValue(categoryFixture({ slug: 'current-category' }));
    apiMocks.getProducts.mockResolvedValue({ items: [], meta: { limit: 100, offset: 0, total: 0 } });

    render(<CategoryPage />);

    await waitFor(() => expect(apiMocks.resolveCategory).toHaveBeenCalledWith('old-category'));
    expect(routerMocks.navigate).toHaveBeenCalledWith(
      '/category/current-category?source=channel',
      { replace: true },
    );
  });
});

function categoryFixture(overrides: Partial<{
  id: number;
  name: string;
  slug: string;
}> = {}) {
  return {
    id: overrides.id ?? 1,
    name: overrides.name ?? 'Category',
    slug: overrides.slug ?? 'futbolki',
    description: null,
    image_path: null,
    image_url: null,
    created_at: '2026-07-03T12:00:00Z',
    updated_at: '2026-07-03T12:00:00Z',
  };
}
