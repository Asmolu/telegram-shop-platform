export class ApiClientError extends Error {
  status: number;
  details: unknown;

  constructor(message: string, status: number, details?: unknown) {
    super(message);
    this.name = 'ApiClientError';
    this.status = status;
    this.details = details;
  }
}

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? '').replace(/\/+$/, '');
const TOKEN_STORAGE_KEY = 'telegram_shop_mini_app_access_token';

export function getApiBaseUrl() {
  return API_BASE_URL;
}

export function getApiOrigin() {
  try {
    return new URL(getApiBaseUrl()).origin;
  } catch {
    return '';
  }
}

export function getStoredAccessToken() {
  return window.localStorage.getItem(TOKEN_STORAGE_KEY);
}

export function storeAccessToken(token: string) {
  window.localStorage.setItem(TOKEN_STORAGE_KEY, token);
}

export function clearStoredAccessToken() {
  window.localStorage.removeItem(TOKEN_STORAGE_KEY);
}

type QueryValue = string | number | boolean | null | undefined;

function buildUrl(path: string, query?: Record<string, QueryValue>) {
  const cleanPath = path.startsWith('/') ? path : `/${path}`;
  const url = new URL(`${getApiBaseUrl()}${cleanPath}`);

  Object.entries(query ?? {}).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') {
      url.searchParams.set(key, String(value));
    }
  });

  return url.toString();
}

function getErrorMessage(payload: unknown, fallback: string) {
  if (typeof payload === 'string') {
    return payload;
  }

  if (payload && typeof payload === 'object' && 'detail' in payload) {
    const detail = (payload as { detail?: unknown }).detail;
    if (typeof detail === 'string') {
      return detail;
    }

    if (Array.isArray(detail)) {
      return detail
        .map((item) => {
          if (item && typeof item === 'object' && 'msg' in item) {
            return String((item as { msg: unknown }).msg);
          }
          return String(item);
        })
        .join('; ');
    }
  }

  return fallback;
}

export async function apiRequest<T>(
  path: string,
  options: RequestInit & { query?: Record<string, QueryValue> } = {},
): Promise<T> {
  const { query, headers, body, ...rest } = options;
  const token = getStoredAccessToken();
  const requestHeaders = new Headers(headers);

  if (body !== undefined && !(body instanceof FormData) && !requestHeaders.has('Content-Type')) {
    requestHeaders.set('Content-Type', 'application/json');
  }

  if (token && !requestHeaders.has('Authorization')) {
    requestHeaders.set('Authorization', `Bearer ${token}`);
  }

  const response = await fetch(buildUrl(path, query), {
    ...rest,
    body,
    headers: requestHeaders,
  });

  if (response.status === 204) {
    return undefined as T;
  }

  const contentType = response.headers.get('content-type') ?? '';
  const payload = contentType.includes('application/json') ? await response.json() : await response.text();

  if (!response.ok) {
    throw new ApiClientError(
      getErrorMessage(payload, 'Не удалось выполнить действие'),
      response.status,
      payload,
    );
  }

  return payload as T;
}

export function isUnauthorizedError(error: unknown) {
  return error instanceof ApiClientError && (error.status === 401 || error.status === 403);
}

const TECHNICAL_MESSAGE_PATTERN =
  /\b(jwt|token|bearer|request|response|fetch|network|backend|api|unauthorized|forbidden|validation|internal|failed|error|dev)\b/i;

const STATUS_ERROR_MESSAGES: Record<number, string> = {
  400: 'Проверьте данные и попробуйте снова.',
  401: 'Войдите через Telegram, чтобы продолжить.',
  403: 'Войдите через Telegram, чтобы продолжить.',
  404: 'Не нашли нужные данные.',
  409: 'Данные изменились. Обновите страницу и попробуйте снова.',
  422: 'Проверьте заполненные поля.',
  429: 'Слишком много действий. Попробуйте позже.',
  500: 'Сервис временно недоступен. Попробуйте позже.',
};

function getStatusErrorMessage(status: number) {
  return STATUS_ERROR_MESSAGES[status] ?? (status >= 500
    ? 'Сервис временно недоступен. Попробуйте позже.'
    : 'Не удалось выполнить действие. Попробуйте снова.');
}

function isUserFacingRussianMessage(message: string) {
  return /[а-яё]/i.test(message) && !TECHNICAL_MESSAGE_PATTERN.test(message);
}

export function toApiErrorMessage(error: unknown) {
  if (error instanceof ApiClientError) {
    return isUserFacingRussianMessage(error.message) ? error.message : getStatusErrorMessage(error.status);
  }

  if (error instanceof Error) {
    return isUserFacingRussianMessage(error.message)
      ? error.message
      : 'Не удалось связаться с сервером. Проверьте интернет и попробуйте снова.';
  }

  return 'Что-то пошло не так';
}
