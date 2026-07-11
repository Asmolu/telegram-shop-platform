import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import React from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  cancelReturnRequest,
  createReturnRequest,
  getOrder,
  getReturnEligibility,
  type Order,
  type ReturnEligibility,
  type ReturnRequest,
} from '../shared/api';
import { ReturnRequestPage } from './ReturnRequestPage';

const routerMocks = vi.hoisted(() => ({
  navigate: vi.fn(),
  route: {
    currentPath: '/orders/99/return',
    pathname: '/orders/99/return',
    searchParams: new URLSearchParams(),
  },
}));

vi.mock('../shared/auth/AuthProvider', () => ({
  useAuth: () => ({ isAuthenticated: true }),
}));

vi.mock('../shared/router/RouterProvider', () => ({
  getAuthPath: (path: string) => `/auth?returnTo=${encodeURIComponent(path)}`,
  getNumericRouteParam: (pathname: string, prefix: string) => Number(pathname.replace(prefix, '').split('/')[0]),
  isFirstLevelRoutePath: () => false,
  useRouter: () => ({
    currentPath: routerMocks.route.currentPath,
    pathname: routerMocks.route.pathname,
    navigate: routerMocks.navigate,
    searchParams: routerMocks.route.searchParams,
  }),
}));

vi.mock('../shared/api', () => ({
  cancelReturnRequest: vi.fn().mockResolvedValue(returnRequestFixture({ status: 'CANCELLED' })),
  createReturnRequest: vi.fn().mockResolvedValue(returnRequestFixture()),
  getApiBaseUrl: vi.fn(() => ''),
  getOrder: vi.fn().mockResolvedValue(orderFixture()),
  getReturnEligibility: vi.fn().mockResolvedValue(returnEligibilityFixture()),
  toApiErrorMessage: (error: unknown) => String(error),
}));

describe('ReturnRequestPage', () => {
  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
    routerMocks.navigate.mockClear();
    vi.mocked(getOrder).mockResolvedValue(orderFixture());
    vi.mocked(getReturnEligibility).mockResolvedValue(returnEligibilityFixture());
    vi.mocked(createReturnRequest).mockResolvedValue(returnRequestFixture());
    vi.mocked(cancelReturnRequest).mockResolvedValue(returnRequestFixture({ status: 'CANCELLED' }));
  });

  it('renders eligible items and submits selected return request', async () => {
    render(<ReturnRequestPage />);

    expect(await screen.findByText('Line Break Hoodie')).toBeTruthy();
    fireEvent.click(screen.getByLabelText('Выбрать товар'));
    fireEvent.change(screen.getByPlaceholderText('Например: не подошёл размер, цвет отличается, обнаружен дефект'), {
      target: { value: 'Не подошёл размер' },
    });
    const photo = new File(['image'], 'proof.jpg', { type: 'image/jpeg' });
    fireEvent.change(screen.getByLabelText(/Фото или видео/), { target: { files: [photo] } });
    fireEvent.click(screen.getByText('Отправить заявку'));

    await waitFor(() => expect(createReturnRequest).toHaveBeenCalledWith(
      99,
      {
        reason: 'Не подошёл размер',
        comment: null,
        items: [{ order_item_id: 1, quantity: 1 }],
      },
      [photo],
    ));
    expect(await screen.findByText('Заявка отправлена. Продавец свяжется с вами.')).toBeTruthy();
    expect(screen.queryByText('✓')).toBeNull();
    expect(document.querySelector('.return-success-card .success-icon')).toBeNull();
    expect(screen.getByText('Статус: Ожидает')).toBeTruthy();
  });

  it('allows cancelling a freshly created pending return request', async () => {
    vi.spyOn(window, 'confirm').mockReturnValueOnce(true);
    render(<ReturnRequestPage />);

    expect(await screen.findByText('Line Break Hoodie')).toBeTruthy();
    fireEvent.click(screen.getByLabelText('Выбрать товар'));
    fireEvent.change(screen.getByPlaceholderText('Например: не подошёл размер, цвет отличается, обнаружен дефект'), {
      target: { value: 'Не подошёл размер' },
    });
    fireEvent.change(screen.getByLabelText(/Фото или видео/), {
      target: { files: [new File(['image'], 'proof.jpg', { type: 'image/jpeg' })] },
    });
    fireEvent.click(screen.getByText('Отправить заявку'));

    expect(await screen.findByText('Отменить заявку')).toBeTruthy();
    fireEvent.click(screen.getByText('Отменить заявку'));

    await waitFor(() => expect(cancelReturnRequest).toHaveBeenCalledWith(7));
    expect(await screen.findByText('Заявка отменена.')).toBeTruthy();
    expect(screen.getByText('Статус: Отменено')).toBeTruthy();
    expect(screen.queryByText('Отменить заявку')).toBeNull();
  });

  it('blocks submit when no items are selected', async () => {
    render(<ReturnRequestPage />);

    expect(await screen.findByText('Line Break Hoodie')).toBeTruthy();
    fireEvent.change(screen.getByPlaceholderText('Например: не подошёл размер, цвет отличается, обнаружен дефект'), {
      target: { value: 'Не подошёл размер' },
    });
    fireEvent.click(screen.getByText('Отправить заявку'));

    expect(await screen.findByText('Выберите хотя бы один товар.')).toBeTruthy();
    expect(createReturnRequest).not.toHaveBeenCalled();
  });

  it('marks media as required and blocks submit without a photo or video', async () => {
    render(<ReturnRequestPage />);

    expect(await screen.findByText('Line Break Hoodie')).toBeTruthy();
    expect(screen.getByText('Фото или видео *')).toBeTruthy();
    expect(screen.getByText('Приложите хотя бы один файл, чтобы продавец мог оценить состояние товара.')).toBeTruthy();
    fireEvent.click(screen.getByLabelText('Выбрать товар'));
    fireEvent.change(screen.getByPlaceholderText('Например: не подошёл размер, цвет отличается, обнаружен дефект'), {
      target: { value: 'Не подошёл размер' },
    });
    fireEvent.click(screen.getByText('Отправить заявку'));

    expect(await screen.findByText('Приложите хотя бы одно фото или видео.')).toBeTruthy();
    expect(createReturnRequest).not.toHaveBeenCalled();
  });

  it('validates unsupported file types and file count', async () => {
    const { container } = render(<ReturnRequestPage />);
    expect(await screen.findByText('Line Break Hoodie')).toBeTruthy();
    const input = container.querySelector<HTMLInputElement>('input[type="file"]');
    expect(input).not.toBeNull();

    fireEvent.change(input!, {
      target: { files: [new File(['x'], 'proof.txt', { type: 'text/plain' })] },
    });
    expect(screen.getByText('Поддерживаются JPEG, PNG, WebP, MP4, WebM или MOV.')).toBeTruthy();

    const files = Array.from({ length: 6 }, (_, index) => (
      new File(['x'], `proof-${index}.jpg`, { type: 'image/jpeg' })
    ));
    fireEvent.change(input!, { target: { files } });
    expect(screen.getByText('Можно прикрепить не больше 5 файлов.')).toBeTruthy();
  });

  it('shows ineligible state without rendering submit', async () => {
    vi.mocked(getReturnEligibility).mockResolvedValueOnce(returnEligibilityFixture({
      eligible: false,
      reason_code: 'return_window_expired',
      message: 'Return window has expired',
    }));

    render(<ReturnRequestPage />);

    expect(await screen.findByText('Возврат недоступен')).toBeTruthy();
    expect(screen.queryByText('Отправить заявку')).toBeNull();
  });
});

function orderFixture(overrides: Partial<Order> = {}): Order {
  return {
    id: 99,
    order_number: 'ORD-000099',
    user_id: 1,
    status: 'DELIVERED',
    subtotal_amount: '200.00',
    discount_amount: '0.00',
    promo_code_id: null,
    promo_code_code: null,
    promo_code: null,
    promo_applied: false,
    total_amount: '200.00',
    subtotal: '200.00',
    discount: '0.00',
    total: '200.00',
    contact_name: 'Ada Lovelace',
    contact_phone: '+79990000000',
    delivery_method: 'CDEK',
    delivery_address: 'Хасавюрт',
    delivery_comment: null,
    manual_payment: null,
    items: [],
    delivered_at: '2026-07-01T00:00:00Z',
    created_at: '2026-06-27T00:00:00Z',
    updated_at: '2026-06-27T00:00:00Z',
    ...overrides,
  };
}

function returnEligibilityFixture(overrides: Partial<ReturnEligibility> = {}): ReturnEligibility {
  return {
    eligible: true,
    reason_code: null,
    message: 'Order is eligible for return',
    return_window_until: '2026-07-11T00:00:00Z',
    order_id: 99,
    return_request_id: null,
    items: [{
      order_item_id: 1,
      product_name: 'Line Break Hoodie',
      product_brand: 'ICON STORE',
      image_url: '/uploads/products/thumb.webp',
      sku: 'SKU-M',
      size: 'M',
      color: 'Black',
      quantity: 2,
      is_returnable: true,
      eligible: true,
      ineligible_reason: null,
    }],
    ...overrides,
  };
}

function returnRequestFixture(overrides: Partial<ReturnRequest> = {}): ReturnRequest {
  return {
    id: 7,
    return_number: 'RET-00000007',
    order_id: 99,
    order_number: 'ORD-000099',
    user_id: 1,
    status: 'PENDING',
    reason: 'Не подошёл размер',
    comment: null,
    items: [],
    attachments: [],
    decided_at: null,
    decided_by_user_id: null,
    decision_comment: null,
    message: 'Заявка отправлена. Продавец свяжется с вами.',
    created_at: '2026-07-01T00:00:00Z',
    updated_at: '2026-07-01T00:00:00Z',
    ...overrides,
  };
}
