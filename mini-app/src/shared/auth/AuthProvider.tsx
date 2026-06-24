import {
  clearStoredAccessToken,
  getCurrentUser,
  getStoredAccessToken,
  loginWithTelegram,
  storeAccessToken,
  toApiErrorMessage,
  type User,
} from '../api';
import { shouldClearStoredTokenAfterAuthError } from './sessionPolicy';
import {
  applyTelegramTheme,
  getTelegramInitData,
  getTelegramRuntimeDiagnostics,
  getTelegramUser,
  initTelegramApp,
  isTelegramWebView,
  subscribeTelegramThemeChanges,
  waitForTelegramWebApp,
  type TelegramUser,
} from '../telegram/webApp';
import React from 'react';

type AuthStatus = 'booting' | 'authenticated' | 'development' | 'error';

type AuthContextValue = {
  status: AuthStatus;
  user: User | null;
  telegramUser: TelegramUser | null;
  error: string | null;
  isAuthenticated: boolean;
  isTelegram: boolean;
  loginWithToken: (token: string) => Promise<void>;
  clearToken: () => void;
  retryTelegramAuth: () => Promise<void>;
};

const AuthContext = React.createContext<AuthContextValue | null>(null);

function logTelegramDiagnostics() {
  if (!import.meta.env.DEV) {
    return;
  }

  console.info('Telegram WebApp detection', getTelegramRuntimeDiagnostics());
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [status, setStatus] = React.useState<AuthStatus>('booting');
  const [user, setUser] = React.useState<User | null>(null);
  const [telegramUser, setTelegramUser] = React.useState<TelegramUser | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  const [isTelegram, setIsTelegram] = React.useState(false);

  const authenticateWithToken = React.useCallback(async (token: string) => {
    storeAccessToken(token);
    const currentUser = await getCurrentUser();
    setUser(currentUser);
    setStatus('authenticated');
    setError(null);
  }, []);

  const runTelegramAuth = React.useCallback(async () => {
    const diagnostics = getTelegramRuntimeDiagnostics();
    setIsTelegram(diagnostics.hasWebApp);
    setTelegramUser(getTelegramUser());
    logTelegramDiagnostics();

    const initData = getTelegramInitData();

    if (!initData) {
      setStatus('development');
      setError(null);
      return;
    }

    try {
      setStatus('booting');
      const result = await loginWithTelegram(initData);
      storeAccessToken(result.access_token);
      setUser(result.user);
      setStatus('authenticated');
      setError(null);
    } catch (authError) {
      if (shouldClearStoredTokenAfterAuthError(authError)) {
        clearStoredAccessToken();
      }
      setUser(null);
      setStatus('error');
      setError(toApiErrorMessage(authError));
      if (import.meta.env.DEV) {
        console.warn(toApiErrorMessage(authError));
      }
    }
  }, []);

  React.useEffect(() => {
    let cancelled = false;
    let unsubscribeTheme: (() => void) | undefined;
    let unsubscribeViewport: (() => void) | undefined;

    async function bootstrap() {
      await waitForTelegramWebApp();
      if (cancelled) {
        return;
      }

      unsubscribeViewport = initTelegramApp();
      applyTelegramTheme();
      unsubscribeTheme = subscribeTelegramThemeChanges(applyTelegramTheme);
      setTelegramUser(getTelegramUser());
      const diagnostics = getTelegramRuntimeDiagnostics();
      setIsTelegram(diagnostics.hasWebApp);
      logTelegramDiagnostics();

      const savedToken = getStoredAccessToken();
      if (savedToken) {
        try {
          const currentUser = await getCurrentUser();
          if (!cancelled) {
            setUser(currentUser);
            setStatus('authenticated');
            setError(null);
          }
          return;
        } catch (tokenError) {
          if (cancelled) {
            return;
          }
          if (!shouldClearStoredTokenAfterAuthError(tokenError)) {
            setStatus('error');
            setError(toApiErrorMessage(tokenError));
            return;
          }
          clearStoredAccessToken();
        }
      }

      if (diagnostics.hasInitData) {
        await runTelegramAuth();
        return;
      }

      if (!cancelled) {
        await runTelegramAuth();
      }
    }

    void bootstrap();

    return () => {
      cancelled = true;
      unsubscribeTheme?.();
      unsubscribeViewport?.();
    };
  }, [runTelegramAuth]);

  const clearToken = React.useCallback(() => {
    clearStoredAccessToken();
    setUser(null);
    setStatus(isTelegramWebView() ? 'booting' : 'development');
    if (isTelegramWebView()) {
      void runTelegramAuth();
    }
  }, [runTelegramAuth]);

  const value = React.useMemo<AuthContextValue>(
    () => ({
      status,
      user,
      telegramUser,
      error,
      isAuthenticated: status === 'authenticated' && Boolean(user),
      isTelegram,
      loginWithToken: authenticateWithToken,
      clearToken,
      retryTelegramAuth: runTelegramAuth,
    }),
    [
      authenticateWithToken,
      clearToken,
      error,
      isTelegram,
      runTelegramAuth,
      status,
      telegramUser,
      user,
    ],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = React.useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within AuthProvider');
  }

  return context;
}
