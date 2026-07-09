import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import React from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { PaymentSuccessBannerController } from './PaymentSuccessBannerController';
import {
  getPendingPaymentSuccessBanner,
  markPaymentSuccessBannerSeen,
} from '../../shared/api';

const apiMocks = vi.hoisted(() => ({
  pending: vi.fn(),
  seen: vi.fn(),
  contacts: vi.fn(),
}));

vi.mock('../../shared/auth/AuthProvider', () => ({
  useAuth: () => ({ isAuthenticated: true }),
}));

vi.mock('../../shared/router/RouterProvider', () => ({
  useRouter: () => ({ currentPath: '/cart' }),
}));

vi.mock('../../shared/api', () => ({
  getApiBaseUrl: () => 'https://api.example.test/api/v1',
  getSellerContactSettings: apiMocks.contacts,
  getPendingPaymentSuccessBanner: apiMocks.pending,
  markPaymentSuccessBannerSeen: apiMocks.seen,
}));

describe('PaymentSuccessBannerController', () => {
  beforeEach(() => {
    window.localStorage.clear();
    apiMocks.pending.mockResolvedValue({
      order_id: 1,
      order_number: 'ORD-000001',
      image_path: 'banners/paid.webp',
      image_url: '/uploads/banners/paid.webp',
      created_at: '2026-07-02T12:00:00Z',
      total_amount: '7262.00',
      delivery_method: 'CDEK',
      payment_status: 'APPROVED',
    });
    apiMocks.contacts.mockResolvedValue({
      telegram_url: 'https://t.me/stylexac',
      whatsapp_url: '',
      instagram_url: null,
    });
    apiMocks.seen.mockResolvedValue({
      order_id: 1,
      seen_at: '2026-07-04T00:00:00Z',
    });
  });

  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it('shows a full-screen paid banner when the pending endpoint returns one', async () => {
    render(<PaymentSuccessBannerController />);

    const overlay = await screen.findByRole('button', {
      name: 'Покупка ORD-000001 завершена',
    });
    const image = overlay.querySelector('img');

    expect(overlay.className).toContain('payment-success-banner-overlay');
    expect(image?.getAttribute('src')).toContain('/uploads/banners/paid.webp');
    expect(screen.getByText('Заказ ORD-000001')).toBeTruthy();
    expect(screen.getByText('Дата покупки: 02 июля 2026')).toBeTruthy();
    expect(screen.getByText('Платёж: Оплачено')).toBeTruthy();
    expect(screen.getByText((_, element) => element?.textContent === 'Сумма: 7 262 ₽')).toBeTruthy();
    expect(getPendingPaymentSuccessBanner).toHaveBeenCalled();
  });

  it('closes on any tap and marks the paid order as seen', async () => {
    render(<PaymentSuccessBannerController />);

    const overlay = await screen.findByRole('button', {
      name: 'Покупка ORD-000001 завершена',
    });
    fireEvent.click(overlay);

    await waitFor(() => {
      expect(screen.queryByRole('button', { name: /Покупка ORD-000001/ })).toBeNull();
    });
    expect(markPaymentSuccessBannerSeen).toHaveBeenCalledWith(1);
  });

  it('does not close when the customer taps the banner image itself', async () => {
    render(<PaymentSuccessBannerController />);

    const overlay = await screen.findByRole('button', {
      name: 'Покупка ORD-000001 завершена',
    });
    const image = overlay.querySelector('img');
    expect(image).not.toBeNull();
    fireEvent.click(image!);

    expect(screen.getByRole('button', { name: /Покупка ORD-000001/ })).toBeTruthy();
    expect(markPaymentSuccessBannerSeen).not.toHaveBeenCalled();
  });

  it('opens seller contacts from the banner data card', async () => {
    render(<PaymentSuccessBannerController />);

    await screen.findByRole('button', {
      name: 'Покупка ORD-000001 завершена',
    });
    fireEvent.click(screen.getByRole('button', { name: 'Связаться с продавцом' }));

    expect(await screen.findByText('Связаться с продавцом в Telegram')).toBeTruthy();
  });

  it('does not render when there is no pending paid banner', async () => {
    apiMocks.pending.mockResolvedValueOnce(null);

    render(<PaymentSuccessBannerController />);

    await waitFor(() => expect(getPendingPaymentSuccessBanner).toHaveBeenCalled());
    expect(screen.queryByRole('button')).toBeNull();
    expect(markPaymentSuccessBannerSeen).not.toHaveBeenCalled();
  });

  it('still closes locally when marking the banner as seen fails', async () => {
    apiMocks.seen.mockRejectedValueOnce(new Error('offline'));

    render(<PaymentSuccessBannerController />);

    const overlay = await screen.findByRole('button', {
      name: 'Покупка ORD-000001 завершена',
    });
    fireEvent.click(overlay);

    await waitFor(() => {
      expect(screen.queryByRole('button', { name: /Покупка ORD-000001/ })).toBeNull();
    });
    expect(markPaymentSuccessBannerSeen).toHaveBeenCalledWith(1);
  });
});
