import React from 'react';
import {
  getTelegramThemeMode,
  subscribeTelegramThemeChanges,
  waitForTelegramWebApp,
  type TelegramColorScheme,
} from '../telegram/webApp';

export type ThemeMode = 'light' | 'dark';
export type ThemePreference = ThemeMode | 'auto';

type ThemeContextValue = {
  theme: ThemeMode;
  themePreference: ThemePreference;
  setTheme: (theme: ThemePreference) => void;
};

const THEME_PREFERENCE_STORAGE_KEY = 'telegram_shop_theme_preference';
const LEGACY_THEME_STORAGE_KEY = 'telegram_shop_theme';
const ThemeContext = React.createContext<ThemeContextValue | null>(null);

function isThemePreference(value: string | null): value is ThemePreference {
  return value === 'auto' || value === 'light' || value === 'dark';
}

function getStoredThemePreference(): ThemePreference {
  try {
    const storedPreference = window.localStorage.getItem(THEME_PREFERENCE_STORAGE_KEY);
    if (isThemePreference(storedPreference)) {
      return storedPreference;
    }

    const legacyTheme = window.localStorage.getItem(LEGACY_THEME_STORAGE_KEY);
    return legacyTheme === 'dark' ? 'dark' : 'auto';
  } catch {
    return 'auto';
  }
}

function applyTheme(theme: ThemeMode, preference: ThemePreference) {
  document.documentElement.dataset.theme = theme;
  document.documentElement.dataset.themePreference = preference;
}

function resolveTheme(
  preference: ThemePreference,
  telegramTheme: TelegramColorScheme | null,
): ThemeMode {
  return preference === 'auto' ? telegramTheme ?? 'light' : preference;
}

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const [themePreference, setTheme] = React.useState<ThemePreference>(() => {
    const storedPreference = getStoredThemePreference();
    applyTheme(resolveTheme(storedPreference, getTelegramThemeMode()), storedPreference);
    return storedPreference;
  });
  const [telegramTheme, setTelegramTheme] = React.useState<TelegramColorScheme | null>(
    () => getTelegramThemeMode(),
  );

  const theme = resolveTheme(themePreference, telegramTheme);

  React.useEffect(() => {
    let cancelled = false;
    let unsubscribe: (() => void) | undefined;

    async function syncTelegramTheme() {
      await waitForTelegramWebApp();
      if (cancelled) {
        return;
      }

      const updateTheme = () => setTelegramTheme(getTelegramThemeMode());
      updateTheme();
      unsubscribe = subscribeTelegramThemeChanges(updateTheme);
    }

    void syncTelegramTheme();

    return () => {
      cancelled = true;
      unsubscribe?.();
    };
  }, []);

  React.useEffect(() => {
    applyTheme(theme, themePreference);
    try {
      window.localStorage.setItem(THEME_PREFERENCE_STORAGE_KEY, themePreference);
    } catch {
      // The selected theme still applies for this session when storage is unavailable.
    }
  }, [theme, themePreference]);

  const value = React.useMemo(
    () => ({ theme, themePreference, setTheme }),
    [theme, themePreference],
  );

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useTheme() {
  const context = React.useContext(ThemeContext);
  if (!context) {
    throw new Error('useTheme must be used within ThemeProvider');
  }

  return context;
}
