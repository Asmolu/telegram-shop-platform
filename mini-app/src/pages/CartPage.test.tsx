import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import React from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { getCart, loginWithTelegram } from '../shared/api';
import { CartPage } from './CartPage';

const getProductMock = vi.hoisted(() => vi.fn());
const routerMocks = vi.hoisted(() => ({
  navigate: vi.fn(),
  searchParams: new URLSearchParams('tab=favorites'),
}));

vi.mock('../shared/auth/AuthProvider', () => ({
  useAuth: () => ({ isAuthenticated: true }),
}));

vi.mock('../shared/router/RouterProvider', () => ({
  getAuthPath: (path: string) => `/auth?returnTo=${encodeURIComponent(path)}`,
  getSafeReturnTo: () => '/main',
  isFirstLevelRoutePath: (path: string) => {
    const url = new URL(path, window.location.origin);
    return ['/', '/main', '/categories', '/search', '/cart', '/profile'].includes(url.pathname);
  },
  Link: ({ children, to, ...props }: React.PropsWithChildren<{ to: string }>) => (
    <a href={to} {...props}>{children}</a>
  ),
  useRouter: () => ({
    currentPath: '/cart',
    navigate: routerMocks.navigate,
    searchParams: routerMocks.searchParams,
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
  getApiBaseUrl: () => 'https://api.example.test/api/v1',
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
        brand: 'ICON STORE',
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
  loginWithTelegram: vi.fn(),
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
    routerMocks.searchParams = new URLSearchParams('tab=favorites');
    routerMocks.navigate.mockClear();
    vi.mocked(getCart).mockClear();
    vi.mocked(loginWithTelegram).mockClear();
    getProductMock.mockClear();
  });

  it('renders the delivery cost hint above the selected row in cart totals', async () => {
    routerMocks.searchParams = new URLSearchParams('tab=cart');
    vi.mocked(getCart).mockResolvedValueOnce(cartWithSelectedItemFixture());

    render(<CartPage />);

    const hint = await screen.findByText('Цена сформирована без учёта стоимости доставки.');
    const summaryCard = hint.closest('.summary-card');

    expect(summaryCard).not.toBeNull();
    const selectedLabel = within(summaryCard as HTMLElement).getByText('Выбрано');
    expect(hint.compareDocumentPosition(selectedLabel) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it('uses products embedded in favorites without per-card detail requests', async () => {
    render(<CartPage />);

    await waitFor(() => expect(screen.getByText('Compact Hoodie')).toBeTruthy());

    expect(getProductMock).not.toHaveBeenCalled();
  });

  it('loads authenticated cart data without requesting fresh Telegram initData', async () => {
    routerMocks.searchParams = new URLSearchParams('tab=cart');

    render(<CartPage />);

    await waitFor(() => expect(getCart).toHaveBeenCalled());
    expect(loginWithTelegram).not.toHaveBeenCalled();
    expect(routerMocks.navigate).not.toHaveBeenCalled();
  });

  it('keeps the promo input visible when focused for the mobile keyboard', async () => {
    routerMocks.searchParams = new URLSearchParams('tab=cart');
    vi.mocked(getCart).mockResolvedValueOnce(cartWithSelectedItemFixture());
    const scrollIntoView = vi.fn();
    Object.defineProperty(HTMLElement.prototype, 'scrollIntoView', {
      configurable: true,
      value: scrollIntoView,
    });

    render(<CartPage />);

    const promoInput = await screen.findByPlaceholderText('Введите промокод');
    fireEvent.focus(promoInput);

    expect(promoInput.closest('.cart-layout')?.classList.contains('cart-layout--promo-focused')).toBe(true);
    await waitFor(() => expect(scrollIntoView).toHaveBeenCalled());
    const focusScrollCalls = scrollIntoView.mock.calls.length;

    fireEvent.change(promoInput, { target: { value: 'SAVE10' } });

    expect((promoInput as HTMLInputElement).value).toBe('SAVE10');
    expect(promoInput.closest('.cart-layout')?.classList.contains('cart-layout--promo-focused')).toBe(true);
    await waitFor(() => expect(scrollIntoView.mock.calls.length).toBeGreaterThan(focusScrollCalls));

    fireEvent.blur(promoInput);

    expect(promoInput.closest('.cart-layout')?.classList.contains('cart-layout--promo-focused')).toBe(false);
  });
});

function cartWithSelectedItemFixture() {
  return {
    id: 1,
    user_id: 1,
    items: [{
      id: 10,
      product: {
        id: 20,
        name: 'Compact Hoodie',
        slug: 'compact-hoodie',
        brand: 'ICON STORE',
        base_price: '100.00',
        old_price: null,
        compare_at_price: null,
        size_grid: 'clothing_alpha' as const,
        status: 'ACTIVE' as const,
        image_url: null,
        thumbnail_image_url: null,
      },
      product_variant: {
        id: 30,
        product_id: 20,
        size: 'M',
        color: 'Black',
        sku: 'SKU-M',
        is_active: true,
        available_quantity: 5,
      },
      quantity: 2,
      is_selected: true,
      unit_price: '100.00',
      subtotal: '200.00',
      created_at: '2026-06-24T00:00:00Z',
      updated_at: '2026-06-24T00:00:00Z',
    }],
    total: '200.00',
    quantity_total: 2,
    distinct_item_count: 1,
    selected_total: '200.00',
    selected_quantity_total: 2,
    selected_distinct_item_count: 1,
    created_at: '2026-06-24T00:00:00Z',
    updated_at: '2026-06-24T00:00:00Z',
  };
}
