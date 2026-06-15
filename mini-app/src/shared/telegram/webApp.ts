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

type TelegramSafeAreaInset = {
  top?: number;
  right?: number;
  bottom?: number;
  left?: number;
};

type TelegramWebAppEvent =
  | 'themeChanged'
  | 'viewportChanged'
  | 'fullscreenChanged'
  | 'safeAreaChanged'
  | 'contentSafeAreaChanged';

export type TelegramWebApp = {
  initData: string;
  initDataUnsafe?: {
    user?: TelegramUser;
  };
  themeParams?: TelegramThemeParams;
  colorScheme?: 'light' | 'dark';
  platform?: string;
  isFullscreen?: boolean;
  safeAreaInset?: TelegramSafeAreaInset;
  contentSafeAreaInset?: TelegramSafeAreaInset;
  onEvent?: (eventType: TelegramWebAppEvent, eventHandler: () => void) => void;
  offEvent?: (eventType: TelegramWebAppEvent, eventHandler: () => void) => void;
  ready?: () => void;
  expand?: () => void;
  requestFullscreen?: () => void;
  exitFullscreen?: () => void;
  disableVerticalSwipes?: () => void;
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

function shouldRequestTelegramFullscreen(webApp: TelegramWebApp | undefined) {
  if (!webApp || typeof webApp.requestFullscreen !== 'function') {
    return false;
  }

  const platform = String(webApp.platform ?? '').toLowerCase();
  const isMobileTelegramPlatform = platform === 'ios'
    || platform === 'android'
    || platform === 'android_x';
  const isLikelyPhoneViewport = typeof window !== 'undefined'
    && window.innerWidth > 0
    && window.innerWidth <= 820;

  return isMobileTelegramPlatform && isLikelyPhoneViewport;
}

function normalizeInset(value: number | undefined) {
  if (!Number.isFinite(value)) {
    return 0;
  }

  return Math.min(Math.max(Number(value), 0), 180);
}

function syncTelegramViewportCss(webApp: TelegramWebApp | undefined, fullscreenRequested: boolean) {
  const root = document.documentElement;
  const platform = String(webApp?.platform ?? '').toLowerCase();
  const mobileTelegram = platform === 'ios'
    || platform === 'android'
    || platform === 'android_x';
  const fullscreen = mobileTelegram && Boolean(webApp?.isFullscreen ?? fullscreenRequested);

  root.dataset.telegramPlatform = platform || 'browser';
  root.dataset.telegramMobile = mobileTelegram ? 'true' : 'false';
  root.dataset.telegramFullscreen = fullscreen ? 'true' : 'false';
  root.style.setProperty('--tg-safe-area-top', `${normalizeInset(webApp?.safeAreaInset?.top)}px`);
  root.style.setProperty(
    '--tg-content-safe-area-top',
    `${normalizeInset(webApp?.contentSafeAreaInset?.top)}px`,
  );
  root.style.setProperty(
    '--tg-fullscreen-top-offset',
    fullscreen ? 'clamp(124px, 31vw, 136px)' : '0px',
  );
}

export function initTelegramApp() {
  const webApp = getTelegramWebApp();
  let fullscreenRequested = false;

  try {
    webApp?.ready?.();
    webApp?.expand?.();
    if (shouldRequestTelegramFullscreen(webApp)) {
      try {
        fullscreenRequested = true;
        webApp?.requestFullscreen?.();
      } catch {
        fullscreenRequested = false;
        // Fullscreen can be unsupported or rejected without blocking startup.
      }
    }
    if (typeof webApp?.disableVerticalSwipes === 'function') {
      webApp.disableVerticalSwipes();
    }
  } catch {
    // Telegram WebApp methods can be unavailable in ordinary browsers.
  }

  const syncViewport = () => {
    if (typeof webApp?.isFullscreen === 'boolean') {
      fullscreenRequested = webApp.isFullscreen;
    }
    syncTelegramViewportCss(webApp, fullscreenRequested);
  };
  const viewportEvents: TelegramWebAppEvent[] = [
    'viewportChanged',
    'fullscreenChanged',
    'safeAreaChanged',
    'contentSafeAreaChanged',
  ];

  syncViewport();
  viewportEvents.forEach((eventType) => webApp?.onEvent?.(eventType, syncViewport));
  window.addEventListener('resize', syncViewport);
  window.visualViewport?.addEventListener('resize', syncViewport);

  return () => {
    viewportEvents.forEach((eventType) => webApp?.offEvent?.(eventType, syncViewport));
    window.removeEventListener('resize', syncViewport);
    window.visualViewport?.removeEventListener('resize', syncViewport);
  };
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

  if (!root.dataset.theme) {
    root.dataset.theme = 'light';
  }
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
