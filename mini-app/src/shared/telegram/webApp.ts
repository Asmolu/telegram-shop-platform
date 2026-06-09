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
  onEvent?: (eventType: 'themeChanged', eventHandler: () => void) => void;
  offEvent?: (eventType: 'themeChanged', eventHandler: () => void) => void;
  ready?: () => void;
  expand?: () => void;
  close?: () => void;
  openTelegramLink?: (url: string) => void;
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

const themeOverrideTokens = [
  '--bg',
  '--surface',
  '--surface-elevated',
  '--text',
  '--text-muted',
  '--border',
  '--primary',
  '--primary-contrast',
];

function normalizeColor(value?: string) {
  if (!value) {
    return null;
  }

  const trimmed = value.trim();
  const shorthand = /^#([a-f\d])([a-f\d])([a-f\d])$/i.exec(trimmed);
  if (shorthand) {
    return `#${shorthand[1]}${shorthand[1]}${shorthand[2]}${shorthand[2]}${shorthand[3]}${shorthand[3]}`;
  }

  if (/^#[a-f\d]{6}$/i.test(trimmed)) {
    return trimmed;
  }

  return null;
}

function hexToRgb(hex: string) {
  const value = Number.parseInt(hex.slice(1), 16);
  return {
    r: (value >> 16) & 255,
    g: (value >> 8) & 255,
    b: value & 255,
  };
}

function getLuminance(hex: string) {
  const { r, g, b } = hexToRgb(hex);
  const channels = [r, g, b].map((channel) => {
    const value = channel / 255;
    return value <= 0.03928 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4;
  });

  return channels[0] * 0.2126 + channels[1] * 0.7152 + channels[2] * 0.0722;
}

function getContrastRatio(left: string, right: string) {
  const lighter = Math.max(getLuminance(left), getLuminance(right));
  const darker = Math.min(getLuminance(left), getLuminance(right));
  return (lighter + 0.05) / (darker + 0.05);
}

function resolveThemeMode(colorScheme?: 'light' | 'dark', bgColor?: string | null) {
  if (colorScheme === 'dark' || colorScheme === 'light') {
    return colorScheme;
  }

  return bgColor && getLuminance(bgColor) < 0.42 ? 'dark' : 'light';
}

function setThemeToken(root: HTMLElement, token: string, color: string | null, contrastAgainst?: string | null, minContrast = 3) {
  if (!color || (contrastAgainst && getContrastRatio(color, contrastAgainst) < minContrast)) {
    return;
  }

  root.style.setProperty(token, color);
}

export function applyTelegramTheme() {
  const webApp = getTelegramWebApp();
  const root = document.documentElement;

  root.dataset.theme = 'light';
  root.dataset.telegram = webApp ? 'true' : 'false';
  themeOverrideTokens.forEach((token) => root.style.removeProperty(token));
}

export function subscribeTelegramThemeChanges(handler: () => void) {
  const webApp = getTelegramWebApp();
  webApp?.onEvent?.('themeChanged', handler);

  return () => {
    webApp?.offEvent?.('themeChanged', handler);
  };
}

export function getTelegramBotUrl() {
  const username = import.meta.env.VITE_TELEGRAM_BOT_USERNAME;
  if (!username) {
    return null;
  }

  return `https://t.me/${String(username).replace(/^@/, '')}`;
}

export function openTelegramLink(url: string) {
  const webApp = getTelegramWebApp();

  try {
    webApp?.openTelegramLink?.(url);
    if (webApp?.openTelegramLink) {
      return;
    }
  } catch {
    // Browser fallback below is used outside Telegram or when the method is unavailable.
  }

  window.open(url, '_blank', 'noopener,noreferrer');
}
