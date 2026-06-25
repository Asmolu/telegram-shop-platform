import { cleanup, render, screen, waitFor } from '@testing-library/react';
import React from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { CartPage } from './CartPage';

const getProductMock = vi.hoisted(() => vi.fn());

vi.mock('../shared/auth/AuthProvider', () => ({
  useAuth: () => ({ isAuthenticated: true }),
}));

vi.mock('../shared/router/RouterProvider', () => ({
  getAuthPath: (path: string) => `/auth?returnTo=${encodeURIComponent(path)}`,
  getSafeReturnTo: () => '/main',
  Link: ({ children, to, ...props }: React.PropsWithChildren<{ to: string }>) => (
    <a href={to} {...props}>{children}</a>
  ),
  useRouter: () => ({
    currentPath: '/cart',
    navigate: vi.fn(),
    searchParams: new URLSearchParams('tab=favorites'),
  }),
  withReturnTo: (path: string) => path,
}));

vi.mock('../features/catalog/useQuickCartPicker', () => ({
  useQuickCartPicker: () => ({
    addToCart: vi.fn(),
    picker: null,
  }),
}));

vi.mock('../shared/api', () => ({
  getApiOrigin: () => 'https://api.example.test',
  getCart: vi.fn().mockResolvedValue({
    id: 1,
    user_id: 1,
    items: [],
    total: '0.00',
    quantity_total: 0,
    distinct_item_count: 0,
    selected_total: '0.00',
    selected_quantity_total: 0,
    selected_distinct_item_count: 0,
    created_at: '2026-06-24T00:00:00Z',
    updated_at: '2026-06-24T00:00:00Z',
  }),
  getFavorites: vi.fn().mockResolvedValue({
    items: [{
      id: 1,
      user_id: 1,
      product_id: 10,
      created_at: '2026-06-24T00:00:00Z',
      product: {
        id: 10,
        name: 'Compact Hoodie',
        slug: 'compact-hoodie',
        brand: 'MENS STYLE',
        base_price: '100.00',
        old_price: null,
        size_grid: 'clothing_alpha',
        image_badge_type: 'none',
        image_badge_text: null,
        image_badge_color: null,
        image_badge_position: null,
        image_url: '/uploads/products/card.webp',
        thumbnail_image_url: '/uploads/products/thumb.webp',
        variants: [],
        is_available: true,
        created_at: '2026-06-24T00:00:00Z',
      },
    }],
  }),
  getOrders: vi.fn().mockResolvedValue({ items: [] }),
  getProduct: getProductMock,
  removeCartItem: vi.fn(),
  removeFavorite: vi.fn(),
  toApiErrorMessage: (error: unknown) => String(error),
  updateCartItem: vi.fn(),
  updateCartItemSelection: vi.fn(),
  updateCartSelection: vi.fn(),
  validatePromoCode: vi.fn(),
}));

describe('CartPage compact favorites', () => {
  afterEach(() => {
    cleanup();
    getProductMock.mockClear();
  });

  it('uses products embedded in favorites without per-card detail requests', async () => {
    render(<CartPage />);

    await waitFor(() => expect(screen.getByText('Compact Hoodie')).toBeTruthy());

    expect(getProductMock).not.toHaveBeenCalled();
  });
});
