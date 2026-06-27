const TOKEN_STORAGE_KEY = 'telegram_shop_mini_app_access_token';

export function getStoredAccessToken() {
  return window.localStorage.getItem(TOKEN_STORAGE_KEY);
}

export function storeAccessToken(token: string) {
  window.localStorage.setItem(TOKEN_STORAGE_KEY, token);
}

export function clearStoredAccessToken() {
  window.localStorage.removeItem(TOKEN_STORAGE_KEY);
}
