import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import React from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { AuthProvider, useAuth } from './AuthProvider';
import { registerAuthSessionRefreshHandler } from './sessionRefresh';

const apiState = vi.hoisted(() => ({
  storedToken: null as string | null,
  user: {
    id: 1,
    telegram_id: 42,
    username: 'buyer',
    first_name: 'Ada',
    last_name: null,
    phone: null,
    role: 'USER',
    is_active: true,
    created_at: '2026-06-28T00:00:00Z',
    updated_at: '2026-06-28T00:00:00Z',
  },
  clearStoredAccessToken: vi.fn(),
  getCurrentUser: vi.fn(),
  getStoredAccessToken: vi.fn(),
  loginWithTelegram: vi.fn(),
  storeAccessToken: vi.fn(),
}));

const telegramState = vi.hoisted(() => ({
  webApp: null as null | {
    initData: string;
    initDataUnsafe?: { user?: { id: number; first_name?: string } };
  },
  initTelegramApp: vi.fn(),
  waitForTelegramInitData: vi.fn(),
  waitForTelegramWebApp: vi.fn(),
}));

vi.mock('../api', () => ({
  clearStoredAccessToken: apiState.clearStoredAccessToken,
  getApiErrorTelemetryCategory: vi.fn(() => 'authentication'),
  getCurrentUser: apiState.getCurrentUser,
  getStoredAccessToken: apiState.getStoredAccessToken,
  loginWithTelegram: apiState.loginWithTelegram,
  storeAccessToken: apiState.storeAccessToken,
  toApiErrorMessage: vi.fn((error: unknown) => (
    error instanceof Error ? error.message : 'auth error'
  )),
}));

vi.mock('../telegram/webApp', () => ({
  applyTelegramTheme: vi.fn(),
  getTelegramRuntimeDiagnostics: () => ({
    hasTelegramObject: Boolean(telegramState.webApp),
    hasWebApp: Boolean(telegramState.webApp),
    hasInitData: Boolean(telegramState.webApp?.initData),
  }),
  getTelegramThemeMode: vi.fn(() => 'light'),
  getTelegramUser: vi.fn(() => telegramState.webApp?.initDataUnsafe?.user ?? null),
  getTelegramWebApp: vi.fn(() => telegramState.webApp ?? undefined),
  initTelegramApp: telegramState.initTelegramApp,
  isTelegramWebView: vi.fn(() => Boolean(telegramState.webApp)),
  subscribeTelegramThemeChanges: vi.fn(() => vi.fn()),
  waitForTelegramInitData: telegramState.waitForTelegramInitData,
  waitForTelegramWebApp: telegramState.waitForTelegramWebApp,
}));

vi.mock('../telemetry', () => ({
  getConnectionTelemetry: vi.fn(() => ({})),
  getViewportTelemetry: vi.fn(() => ({})),
  trackTelemetry: vi.fn(),
}));

function AuthProbe() {
  const auth = useAuth();

  return (
    <div>
      <span data-testid="status">{auth.status}</span>
      <span data-testid="error">{auth.error}</span>
      <button type="button" onClick={() => void auth.retryTelegramAuth()}>
        retry
      </button>
    </div>
  );
}

describe('AuthProvider Telegram initData flow', () => {
  beforeEach(() => {
    apiState.storedToken = null;
    apiState.clearStoredAccessToken.mockImplementation(() => {
      apiState.storedToken = null;
    });
    apiState.getStoredAccessToken.mockImplementation(() => apiState.storedToken);
    apiState.storeAccessToken.mockImplementation((token: string) => {
      apiState.storedToken = token;
    });
    apiState.getCurrentUser.mockResolvedValue(apiState.user);
    apiState.loginWithTelegram.mockResolvedValue({
      access_token: 'fresh-jwt',
      token_type: 'bearer',
      user: apiState.user,
    });
    telegramState.webApp = {
      initData: 'signed-init-data',
      initDataUnsafe: { user: { id: 42, first_name: 'Ada' } },
    };
    telegramState.initTelegramApp.mockReturnValue(vi.fn());
    telegramState.waitForTelegramWebApp.mockImplementation(async () => telegramState.webApp);
    telegramState.waitForTelegramInitData.mockImplementation(
      async () => telegramState.webApp?.initData ?? '',
    );
  });

  afterEach(() => {
    cleanup();
    registerAuthSessionRefreshHandler(async () => false)();
    vi.clearAllMocks();
  });

  it('does not call Telegram login before initData is available', async () => {
    telegramState.webApp = {
      initData: '',
      initDataUnsafe: { user: { id: 42, first_name: 'Ada' } },
    };
    let resolveInitData: (value: string) => void = () => undefined;
    telegramState.waitForTelegramInitData.mockImplementation(() => (
      new Promise<string>((resolve) => {
        resolveInitData = resolve;
      })
    ));

    render(
      <AuthProvider>
        <AuthProbe />
      </AuthProvider>,
    );

    await waitFor(() => expect(telegramState.waitForTelegramInitData).toHaveBeenCalled());
    expect(apiState.loginWithTelegram).not.toHaveBeenCalled();

    await act(async () => {
      resolveInitData('signed-init-data');
    });

    await waitFor(() => expect(apiState.loginWithTelegram).toHaveBeenCalledTimes(1));
    expect(apiState.loginWithTelegram).toHaveBeenCalledWith('signed-init-data');
    expect(screen.getByTestId('status').textContent).toBe('authenticated');
  });

  it('does not issue duplicate Telegram login calls while one is in flight', async () => {
    let resolveLogin: (value: unknown) => void = () => undefined;
    apiState.loginWithTelegram.mockImplementation(() => (
      new Promise((resolve) => {
        resolveLogin = resolve;
      })
    ));

    render(
      <AuthProvider>
        <AuthProbe />
      </AuthProvider>,
    );

    await waitFor(() => expect(apiState.loginWithTelegram).toHaveBeenCalledTimes(1));
    fireEvent.click(screen.getByRole('button', { name: 'retry' }));
    fireEvent.click(screen.getByRole('button', { name: 'retry' }));
    expect(apiState.loginWithTelegram).toHaveBeenCalledTimes(1);

    await act(async () => {
      resolveLogin({
        access_token: 'fresh-jwt',
        token_type: 'bearer',
        user: apiState.user,
      });
    });

    await waitFor(() => expect(screen.getByTestId('status').textContent).toBe('authenticated'));
  });

  it('keeps a valid backend JWT when Telegram initData is transiently empty', async () => {
    apiState.storedToken = 'stored-jwt';
    telegramState.webApp = {
      initData: '',
      initDataUnsafe: { user: { id: 42, first_name: 'Ada' } },
    };

    render(
      <AuthProvider>
        <AuthProbe />
      </AuthProvider>,
    );

    await waitFor(() => expect(screen.getByTestId('status').textContent).toBe('authenticated'));
    expect(apiState.getCurrentUser).toHaveBeenCalledWith({ authRetry: false });
    expect(apiState.loginWithTelegram).not.toHaveBeenCalled();
    expect(apiState.storedToken).toBe('stored-jwt');
  });
});
