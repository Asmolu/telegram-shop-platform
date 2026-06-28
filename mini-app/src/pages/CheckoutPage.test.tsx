import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import React from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  checkoutCart,
  getCustomerNotificationSubscription,
  recordCustomerNotificationWriteAccess,
  type CustomerNotificationSubscription,
} from '../shared/api';
import { openTelegramLink, requestTelegramWriteAccess } from '../shared/telegram/webApp';
import { CheckoutPage } from './CheckoutPage';

const routerMocks = vi.hoisted(() => ({
  navigate: vi.fn(),
  searchParams: new URLSearchParams(),
}));

vi.mock('../shared/auth/AuthProvider', () => ({
  useAuth: () => ({
    isAuthenticated: true,
    telegramUser: { id: 42, first_name: 'Ada', username: 'buyer' },
    user: { id: 1, first_name: 'Ada', username: 'buyer', phone: '+79990000000' },
  }),
}));

vi.mock('../shared/router/RouterProvider', () => ({
  getAuthPath: (path: string) => `/auth?returnTo=${encodeURIComponent(path)}`,
  getSafeReturnTo: () => '/main',
  useRouter: () => ({
    currentPath: '/checkout',
    navigate: routerMocks.navigate,
    searchParams: routerMocks.searchParams,
  }),
  withReturnTo: (path: string) => path,
}));

vi.mock('../shared/telemetry', () => ({
  hashCorrelationKey: vi.fn().mockResolvedValue('hash'),
  trackTelemetry: vi.fn(),
}));

vi.mock('../shared/telegram/webApp', () => ({
  openTelegramLink: vi.fn(),
  requestTelegramWriteAccess: vi.fn(),
}));

vi.mock('../shared/api', () => ({
  checkoutCart: vi.fn().mockResolvedValue({ id: 99 }),
  createIdempotencyKey: vi.fn(() => 'checkout-key'),
  getApiErrorTelemetryCategory: vi.fn(() => 'unknown'),
  getCart: vi.fn().mockResolvedValue(cartFixture()),
  getCustomerNotificationSubscription: vi.fn().mockResolvedValue(subscriptionFixture()),
  getPersonalData: vi.fn().mockResolvedValue(null),
  isTemporaryNetworkError: vi.fn(() => false),
  recordCustomerNotificationWriteAccess: vi.fn().mockResolvedValue(
    subscriptionFixture({
      service_notifications_available: true,
      availability_status: 'available',
      service_opt_in: true,
      write_access_granted: true,
      write_access_granted_at: '2026-06-28T00:00:00Z',
    }),
  ),
  toApiErrorMessage: (error: unknown) => String(error),
  validatePromoCode: vi.fn(),
}));

describe('CheckoutPage notification write access', () => {
  afterEach(() => {
    cleanup();
    routerMocks.navigate.mockClear();
    routerMocks.searchParams = new URLSearchParams();
    vi.mocked(checkoutCart).mockClear();
    vi.mocked(getCustomerNotificationSubscription).mockResolvedValue(subscriptionFixture());
    vi.mocked(recordCustomerNotificationWriteAccess).mockClear();
    vi.mocked(recordCustomerNotificationWriteAccess).mockResolvedValue(
      subscriptionFixture({
        service_notifications_available: true,
        availability_status: 'available',
        service_opt_in: true,
        write_access_granted: true,
        write_access_granted_at: '2026-06-28T00:00:00Z',
      }),
    );
    vi.mocked(requestTelegramWriteAccess).mockReset();
    vi.mocked(openTelegramLink).mockReset();
  });

  it('renders the permission prompt before checkout without requesting write access automatically', async () => {
    render(<CheckoutPage />);

    expect(await screen.findByText('Разрешить уведомления о заказе в Telegram?')).toBeTruthy();
    expect(screen.getByText('Мы сможем прислать статус заказа: принят, в пути, доставлен.')).toBeTruthy();
    expect(requestTelegramWriteAccess).not.toHaveBeenCalled();
  });

  it('requests Telegram write access only after user click and persists granted result', async () => {
    vi.mocked(requestTelegramWriteAccess).mockResolvedValue('granted');

    render(<CheckoutPage />);
    fireEvent.click(await screen.findByRole('button', { name: 'Разрешить уведомления' }));

    await waitFor(() => {
      expect(requestTelegramWriteAccess).toHaveBeenCalledTimes(1);
      expect(recordCustomerNotificationWriteAccess).toHaveBeenCalledWith({
        granted: true,
        source: 'mini_app_request_write_access',
      });
    });
    expect(await screen.findByText('Уведомления о заказах включены')).toBeTruthy();
  });

  it('records denied result and shows the Bot 1 fallback link', async () => {
    vi.mocked(requestTelegramWriteAccess).mockResolvedValue('denied');
    vi.mocked(recordCustomerNotificationWriteAccess).mockResolvedValueOnce(
      subscriptionFixture({
        availability_status: 'permission_denied',
        write_access_denied_at: '2026-06-28T00:00:00Z',
      }),
    );

    render(<CheckoutPage />);
    fireEvent.click(await screen.findByRole('button', { name: 'Разрешить уведомления' }));

    expect(await screen.findByText('Можно подключить уведомления через Bot 1')).toBeTruthy();
    expect(screen.getByText('https://t.me/CheckYouStyleBot?start=notifications')).toBeTruthy();
    expect(recordCustomerNotificationWriteAccess).toHaveBeenCalledWith({
      granted: false,
      source: 'mini_app_request_write_access',
    });

    fireEvent.click(screen.getByRole('button', { name: 'Открыть Bot 1' }));
    expect(openTelegramLink).toHaveBeenCalledWith('https://t.me/CheckYouStyleBot?start=notifications');
  });

  it('shows the Bot 1 fallback when requestWriteAccess is unavailable', async () => {
    vi.mocked(requestTelegramWriteAccess).mockResolvedValue('unavailable');

    render(<CheckoutPage />);
    fireEvent.click(await screen.findByRole('button', { name: 'Разрешить уведомления' }));

    expect(await screen.findByText('Откройте Bot 1, чтобы получать статусы заказа')).toBeTruthy();
    expect(screen.getByText('https://t.me/CheckYouStyleBot?start=notifications')).toBeTruthy();
    expect(recordCustomerNotificationWriteAccess).not.toHaveBeenCalled();
  });
});

function subscriptionFixture(
  overrides: Partial<CustomerNotificationSubscription> = {},
): CustomerNotificationSubscription {
  return {
    has_chat: false,
    write_access_granted: false,
    service_notifications_available: false,
    availability_status: 'permission_required',
    availability_reason: 'no_private_chat_or_write_access',
    service_opt_in: false,
    marketing_opt_in: false,
    blocked_at: null,
    write_access_granted_at: null,
    write_access_denied_at: null,
    telegram_username: null,
    bot_start_link: 'https://t.me/CheckYouStyleBot?start=notifications',
    start_command: '/start notifications',
    ...overrides,
  };
}

function cartFixture() {
  return {
    id: 1,
    user_id: 1,
    items: [
      {
        id: 10,
        product: {
          id: 20,
          name: 'Compact Hoodie',
          slug: 'compact-hoodie',
          brand: 'MENS STYLE',
          base_price: '100.00',
          old_price: null,
          compare_at_price: null,
          size_grid: 'clothing_alpha',
          status: 'ACTIVE',
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
        quantity: 1,
        is_selected: true,
        unit_price: '100.00',
        subtotal: '100.00',
        created_at: '2026-06-24T00:00:00Z',
        updated_at: '2026-06-24T00:00:00Z',
      },
    ],
    total: '100.00',
    quantity_total: 1,
    distinct_item_count: 1,
    selected_total: '100.00',
    selected_quantity_total: 1,
    selected_distinct_item_count: 1,
    created_at: '2026-06-24T00:00:00Z',
    updated_at: '2026-06-24T00:00:00Z',
  };
}
