import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import React from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { StatusNotificationController } from './StatusNotificationController';

const api = vi.hoisted(() => ({ pending: vi.fn(), seen: vi.fn(), contacts: vi.fn() }));

vi.mock('../../shared/auth/AuthProvider', () => ({
  useAuth: () => ({ isAuthenticated: true }),
}));
vi.mock('../../shared/router/RouterProvider', () => ({
  useRouter: () => ({ currentPath: '/orders' }),
}));
vi.mock('../../shared/api', () => ({
  getApiBaseUrl: () => 'https://api.example.test/api/v1',
  getPendingCustomerInAppNotifications: api.pending,
  markCustomerInAppNotificationSeen: api.seen,
  getSellerContactSettings: api.contacts,
}));

const standard = {
  id: 1,
  category: 'order',
  event_code: 'PROCESSING',
  variant: 'standard',
  action_mode: 'continue_only',
  order_id: 10,
  manual_payment_id: null,
  return_request_id: null,
  title: 'Заказ принят в обработку',
  message: 'Заказ ORD-000010 принят продавцом и готовится к отправке.',
  payload: { order_number: 'ORD-000010', order_status: 'PROCESSING' },
  occurred_at: '2026-07-13T10:00:00Z',
  created_at: '2026-07-13T10:00:00Z',
};

const approved = {
  ...standard,
  id: 2,
  category: 'payment',
  event_code: 'APPROVED',
  variant: 'approved_payment',
  action_mode: 'continue_with_contacts',
  title: 'Оплата подтверждена',
  message: 'Оплата заказа ORD-000010 подтверждена.',
  payload: {
    order_number: 'ORD-000010', payment_status: 'APPROVED', order_status: 'PROCESSING',
    total_amount: '7262.00', delivery_method: 'CDEK',
    order_created_at: '2026-07-02T12:00:00Z', image_url: '/uploads/paid.webp',
  },
};

describe('StatusNotificationController', () => {
  beforeEach(() => {
    api.pending.mockResolvedValue([standard]);
    api.seen.mockResolvedValue({ id: 1, seen_at: '2026-07-13T11:00:00Z' });
    api.contacts.mockResolvedValue({ telegram_url: 'https://t.me/stylexac' });
  });
  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
    vi.useRealTimers();
  });

  it('fetches and displays the oldest notification', async () => {
    render(<StatusNotificationController />);
    expect(await screen.findByRole('dialog')).toBeTruthy();
    expect(screen.getByText(standard.title)).toBeTruthy();
    expect(api.pending).toHaveBeenCalled();
  });

  it('acknowledges on Continue and then displays the next queued item', async () => {
    api.pending.mockResolvedValueOnce([standard, approved]);
    render(<StatusNotificationController />);
    await screen.findByText(standard.title);
    fireEvent.click(screen.getByRole('button', { name: 'Продолжить' }));
    await waitFor(() => expect(api.seen).toHaveBeenCalledWith(1));
    expect(await screen.findByText(approved.title)).toBeTruthy();
  });

  it('keeps the current popup visible when acknowledgement fails', async () => {
    api.seen.mockRejectedValueOnce(new Error('offline'));
    render(<StatusNotificationController />);
    await screen.findByText(standard.title);
    fireEvent.click(screen.getByRole('button', { name: 'Продолжить' }));
    expect(await screen.findByRole('alert')).toBeTruthy();
    expect(screen.getByText(standard.title)).toBeTruthy();
  });

  it('renders a photo and five icon/data rows only for approved payment', async () => {
    api.pending.mockResolvedValueOnce([approved]);
    render(<StatusNotificationController />);
    const dialog = await screen.findByRole('dialog');
    expect(dialog.querySelector('img')?.getAttribute('src')).toContain('/uploads/paid.webp');
    expect(dialog.querySelectorAll('.status-notification-data-row')).toHaveLength(5);
    expect(screen.getByText('Необходимо связаться с продавцом для оплаты доставки.')).toBeTruthy();
    expect(screen.queryByText('APPROVED')).toBeNull();
  });

  it('opens seller contacts without marking the notification seen', async () => {
    api.pending.mockResolvedValueOnce([approved]);
    render(<StatusNotificationController />);
    fireEvent.click(await screen.findByRole('button', { name: 'Связаться с продавцом' }));
    expect(await screen.findByText(/Telegram/)).toBeTruthy();
    expect(api.seen).not.toHaveBeenCalled();
  });

  it('does not acknowledge on Escape or backdrop interaction', async () => {
    render(<StatusNotificationController />);
    const dialog = await screen.findByRole('dialog');
    fireEvent.keyDown(dialog, { key: 'Escape' });
    fireEvent.mouseDown(dialog.parentElement!);
    expect(api.seen).not.toHaveBeenCalled();
    expect(screen.getByText(standard.title)).toBeTruthy();
  });
});
