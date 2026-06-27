import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import React from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { ProductDetailPage } from './ProductDetailPage';
import type { Product } from '../shared/api';
import { readFileSync } from 'node:fs';

const apiMocks = vi.hoisted(() => ({
  addCartItem: vi.fn(),
  addFavorite: vi.fn(),
  createProductReview: vi.fn(),
  getCart: vi.fn(),
  getFavorites: vi.fn(),
  getProduct: vi.fn(),
  getProductReviews: vi.fn(),
  removeFavorite: vi.fn(),
}));

const routerMocks = vi.hoisted(() => ({
  navigate: vi.fn(),
  goBack: vi.fn(),
}));

vi.mock('../shared/api', () => ({
  addCartItem: apiMocks.addCartItem,
  addFavorite: apiMocks.addFavorite,
  createProductReview: apiMocks.createProductReview,
  getCart: apiMocks.getCart,
  getFavorites: apiMocks.getFavorites,
  getProduct: apiMocks.getProduct,
  getProductReviews: apiMocks.getProductReviews,
  removeFavorite: apiMocks.removeFavorite,
  toApiErrorMessage: (error: unknown) => error instanceof Error ? error.message : String(error),
}));

vi.mock('../shared/auth/AuthProvider', () => ({
  useAuth: () => ({ isAuthenticated: true }),
}));

vi.mock('../shared/router/RouterProvider', () => ({
  getAuthPath: (path: string) => `/auth?returnTo=${encodeURIComponent(path)}`,
  getNumericRouteParam: (pathname: string, prefix: string) => Number(pathname.slice(prefix.length)),
  Link: ({ children, to, ...props }: React.PropsWithChildren<{ to: string }>) => (
    <a href={to} {...props}>{children}</a>
  ),
  useRouter: () => ({
    currentPath: '/product/10',
    pathname: '/product/10',
    navigate: routerMocks.navigate,
    goBack: routerMocks.goBack,
  }),
  withReturnTo: (path: string) => path,
}));

describe('ProductDetailPage description', () => {
  afterEach(() => {
    vi.clearAllMocks();
  });

  it('renders the size fit hint between product info and variants', async () => {
    apiMocks.getProduct.mockResolvedValue(productFixture());
    apiMocks.getProductReviews.mockResolvedValue({ items: [] });
    apiMocks.getFavorites.mockResolvedValue({ items: [] });
    apiMocks.getCart.mockResolvedValue(cartFixture());

    const { container } = render(<ProductDetailPage />);

    const hint = await screen.findByText('Мы подбираем размер по росту и весу.');
    const productInfoCard = container.querySelector('.product-gallery + .detail-card');
    const variantCard = container.querySelector('.variant-selector-card');

    expect(hint.closest('.product-fit-hint')).not.toBeNull();
    expect(productInfoCard).not.toBeNull();
    expect(variantCard).not.toBeNull();
    expect(productInfoCard!.compareDocumentPosition(hint) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(hint.compareDocumentPosition(variantCard!) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it('preserves newline text rendering in collapsed and expanded states', async () => {
    const styles = readFileSync('src/styles.css', 'utf-8');
    const description = [
      'MONCLER',
      'Комплект футболка-штаны',
      'Сезон: весна/лето',
      'Размеры: М L XL XXL 3XL',
      'Размер подберем по росту и весу',
    ].join('\n');
    apiMocks.getProduct.mockResolvedValue(productFixture({ description }));
    apiMocks.getProductReviews.mockResolvedValue({ items: [] });
    apiMocks.getFavorites.mockResolvedValue({ items: [] });
    apiMocks.getCart.mockResolvedValue(cartFixture());

    const { container } = render(<ProductDetailPage />);

    expect(await screen.findByText('MONCLER', { exact: false })).toBeTruthy();
    const copy = container.querySelector<HTMLParagraphElement>('.description-card__copy');
    expect(copy).not.toBeNull();
    expect(copy?.textContent).toBe(description);
    expect(copy?.classList.contains('is-collapsed')).toBe(true);
    expect(styles).toMatch(/\.description-card__copy\s*{[^}]*white-space:\s*pre-line/s);

    const toggle = container.querySelector<HTMLButtonElement>('.description-card__toggle');
    expect(toggle).not.toBeNull();
    fireEvent.click(toggle!);

    await waitFor(() => expect(copy?.classList.contains('is-collapsed')).toBe(false));
    expect(copy?.textContent).toBe(description);
  });
});

function productFixture(overrides: Partial<Product> = {}): Product {
  return {
    id: 10,
    name: 'Line Break Hoodie',
    slug: 'line-break-hoodie',
    brand: 'MENS STYLE',
    description: null,
    base_price: '1000.00',
    old_price: null,
    compare_at_price: null,
    size_grid: 'clothing_alpha',
    image_badge_type: 'none',
    image_badge_text: null,
    image_badge_color: null,
    image_badge_position: null,
    images: [],
    variants: [{
      id: 100,
      product_id: 10,
      size: 'M',
      color: null,
      sku: 'SKU-M',
      available_quantity: 3,
      is_active: true,
    }],
    is_available: true,
    created_at: '2026-06-27T00:00:00Z',
    ...overrides,
  };
}

function cartFixture() {
  return {
    id: 1,
    user_id: 1,
    items: [],
    total: '0.00',
    quantity_total: 0,
    distinct_item_count: 0,
    selected_total: '0.00',
    selected_quantity_total: 0,
    selected_distinct_item_count: 0,
    created_at: '2026-06-27T00:00:00Z',
    updated_at: '2026-06-27T00:00:00Z',
  };
}
