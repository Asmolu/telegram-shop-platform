import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import React from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import appSource from '../../App.tsx?raw';
import { StatusNotificationController } from './StatusNotificationController';

const api = vi.hoisted(() => ({ pending: vi.fn(), seen: vi.fn(), contacts: vi.fn() }));
const appContext = vi.hoisted(() => ({ isAuthenticated: true, currentPath: '/orders' }));

vi.mock('../../shared/auth/AuthProvider', () => ({
  useAuth: () => ({ isAuthenticated: appContext.isAuthenticated }),
}));
vi.mock('../../shared/router/RouterProvider', () => ({
  useRouter: () => ({ currentPath: appContext.currentPath }),
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
    appContext.isAuthenticated = true;
    appContext.currentPath = '/orders';
    Object.defineProperty(document, 'visibilityState', { configurable: true, value: 'visible' });
    window.localStorage.clear();
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
    expect(screen.getByText(standard.message)).toBeTruthy();
    expect(api.pending).toHaveBeenCalled();
  });

  it('is the only global status controller mounted by App', () => {
    expect(appSource.match(/<StatusNotificationController\s*\/>/g)).toHaveLength(1);
    expect(appSource).not.toContain('<PaymentSuccessBannerController');
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

  it('renders the simplified approved-payment popup with its image and actions', async () => {
    api.pending.mockResolvedValueOnce([approved]);
    render(<StatusNotificationController />);
    const dialog = await screen.findByRole('dialog');
    const image = dialog.querySelector('img');
    expect(image?.getAttribute('src')).toContain('/uploads/paid.webp');
    expect(image?.classList.contains('status-notification-image--approved-payment')).toBe(true);
    expect(dialog.classList.contains('status-notification-card--approved_payment')).toBe(true);
    expect(dialog.parentElement?.classList.contains('status-notification-overlay--approved_payment')).toBe(true);
    expect(screen.getByRole('heading', { name: 'Оплата подтверждена' })).toBeTruthy();
    expect(screen.queryByText(approved.message)).toBeNull();
    expect(screen.queryByText('Заказ')).toBeNull();
    expect(screen.queryByText('Статус заказа')).toBeNull();
    expect(screen.getByText('Дата покупки').parentElement?.textContent).toContain('02 июля 2026');
    expect(screen.getByText('Платёж').parentElement?.textContent).toContain('Оплачено');
    expect(screen.getByText('Сумма').parentElement?.textContent).toMatch(/7\s?262/);
    expect(dialog.querySelectorAll('.status-notification-data-row')).toHaveLength(3);
    expect(screen.getByText('Необходимо связаться с продавцом для оплаты доставки.')).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Связаться с продавцом' })).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Продолжить' })).toBeTruthy();
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

  it('refreshes on route, focus, visibility, and visible polling but pauses while hidden', async () => {
    vi.useFakeTimers();
    api.pending.mockResolvedValue([]);
    const view = render(<StatusNotificationController />);
    await act(async () => Promise.resolve());
    expect(api.pending).toHaveBeenCalledTimes(1);

    appContext.currentPath = '/profile';
    view.rerender(<StatusNotificationController />);
    await act(async () => Promise.resolve());
    expect(api.pending).toHaveBeenCalledTimes(2);

    fireEvent.focus(window);
    await act(async () => Promise.resolve());
    expect(api.pending).toHaveBeenCalledTimes(3);

    fireEvent(document, new Event('visibilitychange'));
    await act(async () => Promise.resolve());
    expect(api.pending).toHaveBeenCalledTimes(4);

    await act(async () => vi.advanceTimersByTimeAsync(45_000));
    expect(api.pending).toHaveBeenCalledTimes(5);

    Object.defineProperty(document, 'visibilityState', { configurable: true, value: 'hidden' });
    await act(async () => vi.advanceTimersByTimeAsync(90_000));
    fireEvent.focus(window);
    fireEvent(document, new Event('visibilitychange'));
    await act(async () => Promise.resolve());
    expect(api.pending).toHaveBeenCalledTimes(5);
  });

  it('does not overlap lifecycle or polling requests', async () => {
    let resolvePending: (value: typeof standard[]) => void = () => undefined;
    api.pending.mockReturnValueOnce(new Promise((resolve) => { resolvePending = resolve; }));
    render(<StatusNotificationController />);
    await act(async () => Promise.resolve());
    fireEvent.focus(window);
    fireEvent(document, new Event('visibilitychange'));
    expect(api.pending).toHaveBeenCalledTimes(1);

    await act(async () => resolvePending([]));
    fireEvent.focus(window);
    await waitFor(() => expect(api.pending).toHaveBeenCalledTimes(2));
  });

  it('locks scroll, traps focus, and restores focus after acknowledgement', async () => {
    const requestAnimationFrame = vi
      .spyOn(window, 'requestAnimationFrame')
      .mockImplementation((callback) => {
        callback(0);
        return 1;
      });
    api.pending.mockResolvedValueOnce([approved]);
    render(<><button type="button">Before popup</button><StatusNotificationController /></>);
    const previous = screen.getByRole('button', { name: 'Before popup' });
    previous.focus();
    const dialog = await screen.findByRole('dialog');
    await waitFor(() => expect(document.activeElement).toBe(dialog));
    expect(document.body.style.overflow).toBe('hidden');

    const buttons = screen.getAllByRole('button').filter((button) => button !== previous);
    const first = buttons[0];
    const last = buttons[buttons.length - 1];
    last.focus();
    fireEvent.keyDown(dialog, { key: 'Tab' });
    expect(document.activeElement).toBe(first);
    first.focus();
    fireEvent.keyDown(dialog, { key: 'Tab', shiftKey: true });
    expect(document.activeElement).toBe(last);

    fireEvent.click(last);
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    expect(document.body.style.overflow).toBe('');
    expect(document.activeElement).toBe(previous);
    requestAnimationFrame.mockRestore();
  });

  it.each(['CDEK', 'WB'])('preserves the delivery contact note for %s', async (deliveryMethod) => {
    api.pending.mockResolvedValueOnce([
      { ...approved, payload: { ...approved.payload, delivery_method: deliveryMethod } },
    ]);
    render(<StatusNotificationController />);
    await screen.findByRole('dialog');
    expect(document.querySelector('.status-notification-delivery-note')).toBeTruthy();
  });

  it.each(['light', 'dark'])('renders the standard button matrix without an image at 320px in %s theme', async (theme) => {
    Object.defineProperty(window, 'innerWidth', { configurable: true, value: 320 });
    document.documentElement.dataset.theme = theme;
    render(<StatusNotificationController />);
    const dialog = await screen.findByRole('dialog');
    expect(dialog.classList.contains('status-notification-card--standard')).toBe(true);
    expect(dialog.parentElement?.classList.contains('status-notification-overlay--approved_payment')).toBe(false);
    expect(dialog.querySelector('img')).toBeNull();
    expect(dialog.querySelector('.status-notification-image--approved-payment')).toBeNull();
    expect(dialog.querySelectorAll('.status-notification-data-row')).toHaveLength(0);
    expect(dialog.querySelectorAll('.status-notification-actions button')).toHaveLength(1);
  });

  it('renders both standard actions when seller contacts are available', async () => {
    api.pending.mockResolvedValueOnce([
      { ...standard, id: 3, event_code: 'CANCELLED', action_mode: 'continue_with_contacts' },
    ]);
    render(<StatusNotificationController />);
    const dialog = await screen.findByRole('dialog');
    expect(dialog.querySelector('img')).toBeNull();
    expect(dialog.querySelectorAll('.status-notification-actions button')).toHaveLength(2);
    expect(screen.queryByText('CANCELLED')).toBeNull();
  });

  it('uses localStorage dismissal only to acknowledge the durable legacy notification', async () => {
    const legacy = {
      ...approved,
      payload: { ...approved.payload, legacy: true },
    };
    window.localStorage.setItem(
      'stylexac.paymentSuccessBanner.dismissedOrderIds',
      JSON.stringify([legacy.order_id]),
    );
    api.pending.mockResolvedValueOnce([legacy]);
    render(<StatusNotificationController />);
    await waitFor(() => expect(api.seen).toHaveBeenCalledWith(legacy.id));
    expect(screen.queryByRole('dialog')).toBeNull();
  });
});
