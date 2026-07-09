import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import React from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  checkoutCart,
  getCart,
  getCustomerNotificationSubscription,
  recordCustomerNotificationWriteAccess,
  validatePromoCode,
  type Cart,
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
  isFirstLevelRoutePath: (path: string) => {
    const url = new URL(path, window.location.origin);
    return ['/', '/main', '/categories', '/search', '/cart', '/profile'].includes(url.pathname);
  },
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
  syncTelegramBackButton: vi.fn(() => () => undefined),
}));

vi.mock('../shared/api', () => ({
  checkoutCart: vi.fn().mockResolvedValue({ id: 99 }),
  createIdempotencyKey: vi.fn(() => 'checkout-key'),
  getApiBaseUrl: vi.fn(() => ''),
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
    vi.mocked(getCart).mockResolvedValue(cartFixture());
    vi.mocked(getCustomerNotificationSubscription).mockResolvedValue(subscriptionFixture());
    vi.mocked(validatePromoCode).mockReset();
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

describe('CheckoutPage item details', () => {
  afterEach(() => {
    cleanup();
    routerMocks.navigate.mockClear();
    routerMocks.searchParams = new URLSearchParams();
    vi.mocked(checkoutCart).mockClear();
    vi.mocked(getCart).mockResolvedValue(cartFixture());
    vi.mocked(getCustomerNotificationSubscription).mockResolvedValue(subscriptionFixture());
    vi.mocked(validatePromoCode).mockReset();
  });

  it('renders selected checkout items with cart-like image, product details, quantity, and price', async () => {
    const { container } = render(<CheckoutPage />);

    const itemCard = await screen.findByText('Compact Hoodie');
    const card = itemCard.closest('.checkout-item-card') as HTMLElement | null;
    const meta = card?.querySelector('.checkout-item-card__meta')?.textContent ?? '';
    const quantity = card?.querySelector('.checkout-item-card__quantity')?.textContent ?? '';
    const price = card?.querySelector('.checkout-item-card__price-row')?.textContent ?? '';

    expect(card).not.toBeNull();
    expect(card?.querySelector('.checkout-item-card__image img')?.getAttribute('src')).toBe('/uploads/products/thumb.webp');
    expect(card?.querySelector('dl')).toBeNull();
    expect(card?.querySelectorAll('dt, dd')).toHaveLength(0);
    expect(screen.getByText('ICON STORE')).toBeTruthy();
    expect(meta).toContain('Black');
    expect(meta).toContain('M');
    expect(meta).toContain('SKU-M');
    expect(quantity).toContain('2');
    expect(quantity).toContain('200');
    expect(price).toContain('100');
    expect(container.querySelector('.promo-form')).toBeTruthy();
  });

  it('keeps long SKU in a single metadata line without table-style field labels', async () => {
    const cart = cartFixture();
    const item = cart.items[0];
    const longSku = 'tshirt1-temno-siniy-3xl-8a7542-extra-long';
    if (!item) {
      throw new Error('Expected cart fixture item');
    }
    item.product.name = 'Футболка Oversize Premium';
    item.product.brand = 'Premium ICON STORE';
    item.product_variant.size = '3XL';
    item.product_variant.color = 'темно-синий';
    item.product_variant.sku = longSku;
    item.quantity = 1;
    item.subtotal = '100.00';
    vi.mocked(getCart).mockResolvedValueOnce(cart);

    render(<CheckoutPage />);

    const title = await screen.findByText('Футболка Oversize Premium');
    const card = title.closest('.checkout-item-card') as HTMLElement | null;
    const meta = card?.querySelector('.checkout-item-card__meta');
    const quantity = card?.querySelector('.checkout-item-card__quantity');

    expect(card).not.toBeNull();
    expect(meta?.textContent).toContain('3XL');
    expect(meta?.textContent).toContain('темно-синий');
    expect(meta?.textContent).toContain(`арт. ${longSku}`);
    expect(quantity?.textContent).toMatch(/Кол-во:\s*1/);
    expect(card?.querySelector('dl')).toBeNull();
    expect(card?.querySelectorAll('dt, dd')).toHaveLength(0);
    expect(within(card as HTMLElement).queryByText('Цвет')).toBeNull();
    expect(within(card as HTMLElement).queryByText('Размер')).toBeNull();
    expect(within(card as HTMLElement).queryByText('Артикул')).toBeNull();
    expect(within(card as HTMLElement).queryByText('Кол-во')).toBeNull();
  });

  it('places enabled order notification status near the bottom of the checkout form', async () => {
    vi.mocked(getCustomerNotificationSubscription).mockResolvedValueOnce(
      subscriptionFixture({
        has_chat: true,
        service_notifications_available: true,
        availability_status: 'available',
        service_opt_in: true,
        write_access_granted: true,
      }),
    );

    const { container } = render(<CheckoutPage />);

    const message = await screen.findByText('Уведомления о заказах включены');
    const checkoutForm = container.querySelector('.checkout-form');
    const promoForm = container.querySelector('.promo-form');
    const submitButton = screen.getByRole('button', { name: 'Оформить заказ' });

    if (!promoForm) {
      throw new Error('Promo form was not rendered');
    }

    expect(message.closest('.checkout-form')).toBe(checkoutForm);
    expect(promoForm.compareDocumentPosition(message) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(message.compareDocumentPosition(submitButton) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it('keeps checkout submit wired after rendering detailed item cards', async () => {
    render(<CheckoutPage />);

    fireEvent.change(await screen.findByLabelText('Адрес (город, улица, номер дома)'), { target: { value: 'Хасавюрт' } });
    fireEvent.click(screen.getByRole('button', { name: 'Оформить заказ' }));

    await waitFor(() => expect(checkoutCart).toHaveBeenCalledWith(
      expect.objectContaining({
        contact_name: 'Ada',
        contact_phone: '+79990000000',
        delivery_address: 'Хасавюрт',
      }),
      'checkout-key',
    ));
  });

  it('allows pickup checkout without address', async () => {
    render(<CheckoutPage />);

    fireEvent.click(await screen.findByRole('radio', { name: /Самовывоз/ }));
    fireEvent.click(screen.getByRole('button', { name: 'Оформить заказ' }));

    await waitFor(() => expect(checkoutCart).toHaveBeenCalledWith(
      expect.objectContaining({
        delivery_method: 'PICKUP',
        delivery_address: '',
      }),
      'checkout-key',
    ));
  });

  it('shows paid delivery price rows and includes delivery in checkout total', async () => {
    render(<CheckoutPage />);

    expect(await screen.findByRole('radio', { name: /Маршруткой\+200/ })).toBeTruthy();
    expect(screen.getByRole('radio', { name: /ВБ доставка\+0/ })).toBeTruthy();
    fireEvent.click(screen.getByRole('radio', { name: /Маршруткой\+200/ }));

    const summary = screen.getByText('Доставка').closest('div');
    expect(summary?.textContent).toContain('200');
    expect(screen.getByText('Итого').closest('div')?.textContent).toContain('400');
  });

  it('shows promo discount before adding delivery to the final total', async () => {
    vi.mocked(validatePromoCode).mockResolvedValueOnce({
      code: 'SAVE50',
      discount_type: 'FIXED',
      discount_value: '50.00',
      subtotal_amount: '200.00',
      discount_amount: '50.00',
      total_amount: '150.00',
    });

    render(<CheckoutPage />);

    fireEvent.change(await screen.findByPlaceholderText('Введите промокод'), { target: { value: 'save50' } });
    fireEvent.click(screen.getByRole('button', { name: 'Применить' }));
    await screen.findByText(/SAVE50/);
    fireEvent.click(screen.getByRole('radio', { name: /Маршруткой\+200/ }));

    expect(screen.getByText('Скидка').closest('div')?.textContent).toContain('50');
    expect(screen.getByText('Доставка').closest('div')?.textContent).toContain('200');
    expect(screen.getByText('Итого').closest('div')?.textContent).toContain('350');
  });

  it('groups Look items in the checkout summary without changing totals', async () => {
    vi.mocked(getCart).mockResolvedValueOnce(cartWithLookGroupFixture());

    render(<CheckoutPage />);

    expect(await screen.findByText('Куплено из образа: City Look')).toBeTruthy();
    expect(screen.getByText('Look Shirt')).toBeTruthy();
    expect(screen.getByText('Look Pants')).toBeTruthy();
    expect(screen.getByText('Compact Hoodie')).toBeTruthy();
    expect(screen.getAllByText(/500/).length).toBeGreaterThan(0);
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

function cartFixture(): Cart {
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
          brand: 'ICON STORE',
          base_price: '100.00',
          old_price: null,
          compare_at_price: null,
          size_grid: 'clothing_alpha',
          status: 'ACTIVE',
          image_url: '/uploads/products/card.webp',
          thumbnail_image_url: '/uploads/products/thumb.webp',
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
      },
    ],
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

function cartWithLookGroupFixture(): Cart {
  const cart = cartFixture();
  return {
    ...cart,
    items: [
      cart.items[0],
      {
        ...cart.items[0],
        id: 11,
        product: {
          ...cart.items[0].product,
          id: 21,
          name: 'Look Shirt',
          slug: 'look-shirt',
        },
        product_variant: {
          ...cart.items[0].product_variant,
          id: 31,
          product_id: 21,
          sku: 'SHIRT-M',
        },
        source_type: 'LOOK',
        source_group_id: 'look-group-1',
        source_look_id: 7,
        source_look_slug: 'city-look',
        source_look_title: 'City Look',
        source_look_image_url: '/uploads/looks/city.webp',
      },
      {
        ...cart.items[0],
        id: 12,
        product: {
          ...cart.items[0].product,
          id: 22,
          name: 'Look Pants',
          slug: 'look-pants',
        },
        product_variant: {
          ...cart.items[0].product_variant,
          id: 32,
          product_id: 22,
          sku: 'PANTS-M',
        },
        quantity: 1,
        subtotal: '100.00',
        source_type: 'LOOK',
        source_group_id: 'look-group-1',
        source_look_id: 7,
        source_look_slug: 'city-look',
        source_look_title: 'City Look',
        source_look_image_url: '/uploads/looks/city.webp',
      },
    ],
    total: '500.00',
    quantity_total: 5,
    distinct_item_count: 3,
    selected_total: '500.00',
    selected_quantity_total: 5,
    selected_distinct_item_count: 3,
  };
}
