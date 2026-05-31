export type TelegramThemeParams = {
  bg_color?: string;
  text_color?: string;
  hint_color?: string;
  link_color?: string;
  button_color?: string;
  button_text_color?: string;
  secondary_bg_color?: string;
};

export type TelegramUser = {
  id: number;
  first_name?: string;
  last_name?: string;
  username?: string;
  photo_url?: string;
};

export type TelegramWebApp = {
  initData: string;
  initDataUnsafe?: {
    user?: TelegramUser;
  };
  themeParams?: TelegramThemeParams;
  colorScheme?: 'light' | 'dark';
  ready?: () => void;
  expand?: () => void;
  close?: () => void;
};

export type TelegramRuntimeDiagnostics = {
  hasTelegramObject: boolean;
  hasWebApp: boolean;
  hasInitData: boolean;
};

declare global {
  interface Window {
    Telegram?: {
      WebApp?: TelegramWebApp;
    };
  }
}

export function getTelegramWebApp() {
  if (typeof window === 'undefined') {
    return undefined;
  }

  return window.Telegram?.WebApp;
}

export function isTelegramWebView() {
  return Boolean(getTelegramWebApp());
}

export function getTelegramRuntimeDiagnostics(): TelegramRuntimeDiagnostics {
  const webApp = getTelegramWebApp();

  return {
    hasTelegramObject: typeof window !== 'undefined' && Boolean(window.Telegram),
    hasWebApp: Boolean(webApp),
    hasInitData: Boolean(webApp?.initData),
  };
}

export async function waitForTelegramWebApp(timeoutMs = 1200, intervalMs = 50) {
  const existingWebApp = getTelegramWebApp();
  if (existingWebApp) {
    return existingWebApp;
  }

  const startedAt = Date.now();

  while (Date.now() - startedAt < timeoutMs) {
    await new Promise((resolve) => window.setTimeout(resolve, intervalMs));

    const webApp = getTelegramWebApp();
    if (webApp) {
      return webApp;
    }
  }

  return getTelegramWebApp();
}

export function getTelegramInitData() {
  return getTelegramWebApp()?.initData ?? '';
}

export function getTelegramUser() {
  return getTelegramWebApp()?.initDataUnsafe?.user ?? null;
}

export function getTelegramThemeParams() {
  return getTelegramWebApp()?.themeParams ?? {};
}

export function initTelegramApp() {
  const webApp = getTelegramWebApp();

  try {
    webApp?.ready?.();
    webApp?.expand?.();
  } catch {
    // Telegram WebApp methods can be unavailable in ordinary browsers.
  }
}

export function applyTelegramTheme() {
  const theme = getTelegramThemeParams();
  const root = document.documentElement;

  if (theme.bg_color) {
    root.style.setProperty('--tg-bg-color', theme.bg_color);
  }

  if (theme.text_color) {
    root.style.setProperty('--tg-text-color', theme.text_color);
  }

  if (theme.button_color) {
    root.style.setProperty('--tg-button-color', theme.button_color);
  }

  if (theme.secondary_bg_color) {
    root.style.setProperty('--tg-secondary-bg-color', theme.secondary_bg_color);
  }
}

export function getTelegramBotUrl() {
  const username = import.meta.env.VITE_TELEGRAM_BOT_USERNAME;
  if (!username) {
    return null;
  }

  return `https://t.me/${String(username).replace(/^@/, '')}`;
}
