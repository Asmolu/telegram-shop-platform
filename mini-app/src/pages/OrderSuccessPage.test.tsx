import { cleanup, render, screen } from '@testing-library/react';
import React from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { getOrder, type Order } from '../shared/api';
import { OrderSuccessPage } from './OrderSuccessPage';

const routerMocks = vi.hoisted(() => ({
  navigate: vi.fn(),
  route: {
    currentPath: '/order-success/99',
    pathname: '/order-success/99',
    searchParams: new URLSearchParams(),
  },
}));

vi.mock('../shared/auth/AuthProvider', () => ({
  useAuth: () => ({ isAuthenticated: true }),
}));

vi.mock('../shared/router/RouterProvider', () => ({
  getAuthPath: (path: string) => `/auth?returnTo=${encodeURIComponent(path)}`,
  getNumericRouteParam: (pathname: string, prefix: string) => Number(pathname.slice(prefix.length)),
  getSafeReturnTo: () => '/main',
  isFirstLevelRoutePath: (path: string) => {
    const url = new URL(path, window.location.origin);
    return ['/', '/main', '/categories', '/search', '/cart', '/profile'].includes(url.pathname);
  },
  Link: ({ children, to, ...props }: React.PropsWithChildren<{ to: string }>) => (
    <a href={to} {...props}>{children}</a>
  ),
  useRouter: () => ({
    currentPath: routerMocks.route.currentPath,
    pathname: routerMocks.route.pathname,
    navigate: routerMocks.navigate,
    searchParams: routerMocks.route.searchParams,
  }),
  withReturnTo: (to: string) => to,
}));

vi.mock('../shared/api', () => ({
  getApiBaseUrl: vi.fn(() => ''),
  getOrder: vi.fn().mockResolvedValue(orderFixture()),
  toApiErrorMessage: (error: unknown) => String(error),
}));

describe('OrderSuccessPage details', () => {
  afterEach(() => {
    cleanup();
    routerMocks.navigate.mockClear();
    routerMocks.route = {
      currentPath: '/order-success/99',
      pathname: '/order-success/99',
      searchParams: new URLSearchParams(),
    };
    vi.mocked(getOrder).mockResolvedValue(orderFixture());
  });

  it('renders order summary, payment status, product details, totals, and delivery data', async () => {
    const { container } = render(<OrderSuccessPage />);

    expect(await screen.findByText('Заказ ORD-00000099')).toBeTruthy();
    expect(screen.getAllByText('Новый').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Оплата на проверке').length).toBeGreaterThan(0);
    expect(screen.getByText('Line Break Hoodie')).toBeTruthy();
    expect(screen.getByText('ICON STORE')).toBeTruthy();
    expect(screen.getByText('Black')).toBeTruthy();
    expect(screen.getByText('M')).toBeTruthy();
    expect(screen.getByText('SKU-M')).toBeTruthy();
    expect(screen.getByText('SAVE10', { exact: false })).toBeTruthy();
    expect(screen.getByText('Ada Lovelace')).toBeTruthy();
    expect(screen.getByText('+79990000000')).toBeTruthy();
    expect(screen.getByText('Рост: 180 · Вес: 75')).toBeTruthy();
    expect(container.querySelector('.order-detail-item__image img')?.getAttribute('src')).toBe('/uploads/products/thumb.webp');
  });

  it('renders missing optional fields gracefully', async () => {
    vi.mocked(getOrder).mockResolvedValueOnce(orderFixture({
      discount_amount: '0.00',
      promo_code: null,
      promo_code_code: null,
      delivery_method: null,
      delivery_comment: null,
      manual_payment: null,
      items: [{
        ...orderFixture().items[0],
        product_brand: null,
        product_thumbnail_url: null,
        product_thumbnail_path: null,
        variant_color: null,
      }],
    }));

    render(<OrderSuccessPage />);

    expect((await screen.findAllByText('Статус оплаты')).length).toBeGreaterThan(0);
    expect(screen.getAllByText('Не указан').length).toBeGreaterThan(0);
    expect(screen.getByText('Line Break Hoodie')).toBeTruthy();
    expect(screen.getByText('Артикул')).toBeTruthy();
  });
});

function orderFixture(overrides: Partial<Order> = {}): Order {
  return {
    id: 99,
    order_number: 'ORD-00000099',
    user_id: 1,
    status: 'NEW',
    subtotal_amount: '200.00',
    discount_amount: '20.00',
    promo_code_id: 7,
    promo_code_code: 'SAVE10',
    promo_code: 'SAVE10',
    promo_applied: true,
    total_amount: '180.00',
    subtotal: '200.00',
    discount: '20.00',
    total: '180.00',
    contact_name: 'Ada Lovelace',
    contact_phone: '+79990000000',
    delivery_method: 'CDEK',
    delivery_address: 'Хасавюрт',
    delivery_comment: 'Рост: 180\nВес: 75',
    manual_payment: {
      id: 1,
      status: 'SUBMITTED',
      expires_at: '2026-06-28T00:00:00Z',
      submitted_at: '2026-06-27T00:00:00Z',
      receipt_image_path: null,
      receipt_image_url: null,
    },
    items: [{
      id: 1,
      product_id: 20,
      product_variant_id: 30,
      product_name: 'Line Break Hoodie',
      product_title: 'Line Break Hoodie',
      product_brand: 'ICON STORE',
      variant_size: 'M',
      variant_size_grid: 'clothing_alpha',
      variant_color: 'Black',
      variant_sku: 'SKU-M',
      unit_price: '100.00',
      quantity: 2,
      subtotal: '200.00',
      item_total: '200.00',
      product_thumbnail_path: 'products/thumb.webp',
      product_thumbnail_url: '/uploads/products/thumb.webp',
      created_at: '2026-06-27T00:00:00Z',
    }],
    created_at: '2026-06-27T00:00:00Z',
    updated_at: '2026-06-27T00:00:00Z',
    ...overrides,
  };
}
