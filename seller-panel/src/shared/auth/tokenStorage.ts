const LOCAL_TOKEN_KEY = 'seller_panel_access_token';
const SESSION_TOKEN_KEY = 'seller_panel_session_access_token';

export type TokenStorageScope = 'local' | 'session';

export function getStoredToken(): string | null {
  return localStorage.getItem(LOCAL_TOKEN_KEY) ?? sessionStorage.getItem(SESSION_TOKEN_KEY);
}

export function getTokenStorageScope(): TokenStorageScope | null {
  if (localStorage.getItem(LOCAL_TOKEN_KEY)) {
    return 'local';
  }

  if (sessionStorage.getItem(SESSION_TOKEN_KEY)) {
    return 'session';
  }

  return null;
}

export function setStoredToken(token: string, scope: TokenStorageScope): void {
  clearStoredToken();

  if (scope === 'local') {
    localStorage.setItem(LOCAL_TOKEN_KEY, token);
    return;
  }

  sessionStorage.setItem(SESSION_TOKEN_KEY, token);
}

export function clearStoredToken(): void {
  localStorage.removeItem(LOCAL_TOKEN_KEY);
  sessionStorage.removeItem(SESSION_TOKEN_KEY);
}
