import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import React from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { ProfilePage } from './ProfilePage';

const openTelegramLink = vi.hoisted(() => vi.fn());

vi.mock('../shared/auth/AuthProvider', () => ({
  useAuth: () => ({
    clearToken: vi.fn(),
    isAuthenticated: true,
    isTelegram: false,
    status: 'authenticated',
    telegramUser: null,
    user: { first_name: 'Ada', username: 'ada' },
  }),
}));

vi.mock('../shared/router/RouterProvider', () => ({
  getAuthPath: (path: string) => path,
  useRouter: () => ({ currentPath: '/profile', navigate: vi.fn() }),
  withReturnTo: (path: string) => path,
}));

vi.mock('../shared/theme/ThemeProvider', () => ({
  useTheme: () => ({ theme: 'light', themePreference: 'auto', setTheme: vi.fn() }),
}));

vi.mock('../shared/telegram/webApp', () => ({
  openTelegramLink,
  requestTelegramWriteAccess: vi.fn(),
}));

vi.mock('../shared/api', () => ({
  createCustomerNotificationStartLink: vi.fn(),
  getCustomerNotificationSubscription: vi.fn().mockResolvedValue({
    has_chat: false,
    service_opt_in: false,
    marketing_opt_in: false,
  }),
  recordCustomerNotificationWriteAccess: vi.fn(),
  toApiErrorMessage: (error: unknown) => String(error),
  updateCustomerNotificationSubscription: vi.fn(),
}));

vi.mock('../shared/ui', () => ({
  EmptyState: () => null,
  TopBar: ({ title }: { title: string }) => <div>{title}</div>,
  SellerContactCard: () => (
    <div data-testid="seller-contact-card">
      <a href="https://t.me/store">Telegram</a>
      <a href="https://wa.me/1">WhatsApp</a>
      <a href="https://instagram.com/store">Instagram</a>
    </div>
  ),
}));

vi.mock('../shared/utils/format', () => ({ getUserDisplayName: () => 'Ada' }));

describe('ProfilePage support contacts', () => {
  afterEach(() => {
    cleanup();
    openTelegramLink.mockClear();
  });

  it('expands and collapses the shared seller contacts without opening Telegram', () => {
    render(<ProfilePage />);
    const support = screen.getByRole('button', { name: /Поддержка/ });

    expect(support.getAttribute('aria-expanded')).toBe('false');
    expect(screen.queryByTestId('seller-contact-card')).toBeNull();
    fireEvent.click(support);
    expect(support.getAttribute('aria-expanded')).toBe('true');
    expect(screen.getByText('Telegram')).toBeTruthy();
    expect(screen.getByText('WhatsApp')).toBeTruthy();
    expect(screen.getByText('Instagram')).toBeTruthy();
    expect(openTelegramLink).not.toHaveBeenCalled();
    fireEvent.click(support);
    expect(screen.queryByTestId('seller-contact-card')).toBeNull();
  });
});
