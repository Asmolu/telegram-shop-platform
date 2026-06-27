import {
  markNetworkRequestFailure,
  markNetworkRequestStarted,
  markNetworkRequestSuccess,
} from '../network/networkState';
import {
  getConnectionTelemetry,
  normalizeEndpointScope,
  trackTelemetry,
} from '../telemetry';
import { getStoredAccessToken } from '../auth/tokenStorage';
import { buildApiUrl, getApiOriginFromBase, normalizeApiBaseUrl } from '../utils/urls';
export { clearStoredAccessToken, getStoredAccessToken, storeAccessToken } from '../auth/tokenStorage';

export type ApiErrorKind =
  | 'authentication'
  | 'validation'
  | 'network_unavailable'
  | 'timeout'
  | 'request_aborted'
  | 'rate_limited'
  | 'temporary_server_failure'
  | 'permanent_server_failure';

export class ApiClientError extends Error {
  status: number;
  kind: ApiErrorKind;
  details: unknown;
  requestId?: string;
  retryAfterMs?: number;

  constructor({
    message,
    status = 0,
    kind,
    details,
    requestId,
    retryAfterMs,
  }: {
    message: string;
    status?: number;
    kind: ApiErrorKind;
    details?: unknown;
    requestId?: string;
    retryAfterMs?: number;
  }) {
    super(message);
    this.name = 'ApiClientError';
    this.status = status;
    this.kind = kind;
    this.details = details;
    this.requestId = requestId;
    this.retryAfterMs = retryAfterMs;
  }
}

const API_BASE_URL = normalizeApiBaseUrl(import.meta.env.VITE_API_BASE_URL);

export const API_TIMEOUT_MS = {
  read: 12_000,
  mutation: 20_000,
  upload: 45_000,
} as const;

const RETRY_POLICY = {
  maxAttempts: 3,
  baseDelayMs: 350,
  maxDelayMs: 2_500,
  jitterMs: 160,
} as const;

const RETRYABLE_STATUSES = new Set([408, 429, 502, 503, 504]);
const inFlightGetRequests = new Map<string, Promise<unknown>>();

type QueryValue = string | number | boolean | null | undefined;

export type ApiRequestOptions = RequestInit & {
  query?: Record<string, QueryValue>;
  timeoutMs?: number;
  retry?: boolean;
  dedupe?: boolean;
  idempotencyKey?: string;
  networkImpact?: 'global' | 'local';
};

export function getApiBaseUrl() {
  return API_BASE_URL;
}

export function getApiOrigin() {
  return getApiOriginFromBase(getApiBaseUrl());
}

export function createIdempotencyKey(prefix = 'miniapp') {
  const randomValue = typeof crypto !== 'undefined' && 'randomUUID' in crypto
    ? crypto.randomUUID()
    : `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`;
  return `${prefix}:${randomValue}`;
}

function buildUrl(path: string, query?: Record<string, QueryValue>) {
  return buildApiUrl(getApiBaseUrl(), path, query);
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
  options: ApiRequestOptions = {},
): Promise<T> {
  const {
    query,
    headers,
    body,
    timeoutMs,
    retry = true,
    dedupe = true,
    idempotencyKey,
    networkImpact = 'global',
    ...rest
  } = options;
  const method = (rest.method ?? 'GET').toUpperCase();
  const url = buildUrl(path, query);
  const canRetry = retry && isRetryableReadRequest(method, path);
  const canDedupe = dedupe && method === 'GET' && isSafeReadPath(path) && !options.signal;
  const dedupeKey = canDedupe ? `${method}:${url}:${Boolean(getStoredAccessToken())}` : null;

  if (dedupeKey) {
    const existing = inFlightGetRequests.get(dedupeKey);
    if (existing) {
      return existing as Promise<T>;
    }
  }

  const request = requestWithRetry<T>({
    body,
    canRetry,
    headers,
    idempotencyKey,
    method,
    networkImpact,
    rest,
    timeoutMs,
    url,
  });

  if (dedupeKey) {
    inFlightGetRequests.set(dedupeKey, request);
    request.then(
      () => inFlightGetRequests.delete(dedupeKey),
      () => inFlightGetRequests.delete(dedupeKey),
    );
  }

  return request;
}

async function requestWithRetry<T>({
  body,
  canRetry,
  headers,
  idempotencyKey,
  method,
  networkImpact,
  rest,
  timeoutMs,
  url,
}: {
  body?: BodyInit | null;
  canRetry: boolean;
  headers?: HeadersInit;
  idempotencyKey?: string;
  method: string;
  networkImpact: 'global' | 'local';
  rest: Omit<RequestInit, 'body' | 'headers'>;
  timeoutMs?: number;
  url: string;
}) {
  const attempts = canRetry ? RETRY_POLICY.maxAttempts : 1;
  let lastError: unknown;

  for (let attempt = 1; attempt <= attempts; attempt += 1) {
    try {
      return await executeRequest<T>({
        body,
        headers,
        idempotencyKey,
        method,
        networkImpact,
        rest,
        timeoutMs,
        url,
        retryCount: attempt - 1,
      });
    } catch (error) {
      lastError = error;
      if (!canRetry || attempt >= attempts || !shouldRetryError(error)) {
        if (canRetry && attempt >= attempts && shouldRetryError(error)) {
          trackTelemetry('api.retry_exhausted', {
            method,
            endpoint_scope: normalizeEndpointScope(new URL(url).pathname),
            retry_count: attempt - 1,
            error_category: getApiErrorTelemetryCategory(error),
            request_id: error instanceof ApiClientError ? error.requestId : undefined,
            ...getConnectionTelemetry(),
          }, { priority: 'critical' });
        }
        throw error;
      }
      trackTelemetry('api.retry_scheduled', {
        method,
        endpoint_scope: normalizeEndpointScope(new URL(url).pathname),
        retry_count: attempt,
        error_category: getApiErrorTelemetryCategory(error),
        request_id: error instanceof ApiClientError ? error.requestId : undefined,
        ...getConnectionTelemetry(),
      });
      await waitForRetryDelay(error, attempt, rest.signal);
      if (networkImpact === 'global') {
        markNetworkRequestStarted();
      }
    }
  }

  throw lastError;
}

async function executeRequest<T>({
  body,
  headers,
  idempotencyKey,
  method,
  networkImpact,
  rest,
  timeoutMs,
  url,
  retryCount,
}: {
  body?: BodyInit | null;
  headers?: HeadersInit;
  idempotencyKey?: string;
  method: string;
  networkImpact: 'global' | 'local';
  rest: Omit<RequestInit, 'body' | 'headers'>;
  timeoutMs?: number;
  url: string;
  retryCount: number;
}) {
  const token = getStoredAccessToken();
  const requestHeaders = new Headers(headers);
  const requestTimeoutMs = timeoutMs ?? getDefaultTimeoutMs(method, body);
  const abort = createTimeoutSignal(rest.signal, requestTimeoutMs);
  const startedAt = Date.now();

  if (body !== undefined && !(body instanceof FormData) && !requestHeaders.has('Content-Type')) {
    requestHeaders.set('Content-Type', 'application/json');
  }

  if (token && !requestHeaders.has('Authorization')) {
    requestHeaders.set('Authorization', `Bearer ${token}`);
  }

  if (idempotencyKey && !requestHeaders.has('Idempotency-Key')) {
    requestHeaders.set('Idempotency-Key', idempotencyKey);
  }

  try {
    const response = await fetch(url, {
      ...rest,
      method,
      body,
      headers: requestHeaders,
      signal: abort.signal,
    });
    const durationMs = Date.now() - startedAt;
    const requestId = response.headers.get('x-request-id') ?? undefined;
    const responseSizeBucket = byteBucket(response.headers.get('content-length'));

    if (response.status === 204) {
      if (networkImpact === 'global') {
        markNetworkRequestSuccess(durationMs);
      }
      trackTelemetry('api.request_completed', {
        method,
        endpoint_scope: normalizeEndpointScope(new URL(url).pathname),
        status: response.status,
        duration_ms: durationMs,
        retry_count: retryCount,
        request_id: requestId,
        response_size_bucket: responseSizeBucket,
        success: true,
        ...getConnectionTelemetry(),
      });
      return undefined as T;
    }

    const contentType = response.headers.get('content-type') ?? '';
    const payload = contentType.includes('application/json')
      ? await response.json()
      : await response.text();

    if (!response.ok) {
      const apiError = createHttpError(response, payload, requestId);
      if (networkImpact === 'global') {
        markNetworkRequestFailure(apiError);
      }
      trackTelemetry('api.request_failed', {
        method,
        endpoint_scope: normalizeEndpointScope(new URL(url).pathname),
        status: response.status,
        duration_ms: durationMs,
        retry_count: retryCount,
        request_id: requestId,
        response_size_bucket: responseSizeBucket,
        error_category: apiError.kind,
        success: false,
        ...getConnectionTelemetry(),
      }, { priority: 'critical' });
      throw apiError;
    }

    if (networkImpact === 'global') {
      markNetworkRequestSuccess(durationMs);
    }
    trackTelemetry('api.request_completed', {
      method,
      endpoint_scope: normalizeEndpointScope(new URL(url).pathname),
      status: response.status,
      duration_ms: durationMs,
      retry_count: retryCount,
      request_id: requestId,
      response_size_bucket: responseSizeBucket,
      success: true,
      ...getConnectionTelemetry(),
    });
    return payload as T;
  } catch (error) {
    if (error instanceof ApiClientError) {
      throw error;
    }
    const normalizedError = createFetchError(error, abort.timedOut);
    if (networkImpact === 'global') {
      markNetworkRequestFailure(normalizedError);
    }
    trackTelemetry('api.request_failed', {
      method,
      endpoint_scope: normalizeEndpointScope(new URL(url).pathname),
      duration_ms: Date.now() - startedAt,
      retry_count: retryCount,
      error_category: normalizedError.kind,
      success: false,
      ...getConnectionTelemetry(),
    }, normalizedError.kind === 'request_aborted' ? undefined : { priority: 'critical' });
    throw normalizedError;
  } finally {
    abort.cleanup();
  }
}

function createHttpError(response: Response, payload: unknown, requestId?: string) {
  const status = response.status;
  return new ApiClientError({
    message: getErrorMessage(payload, 'Не удалось выполнить действие'),
    status,
    kind: classifyHttpStatus(status),
    details: payload,
    requestId,
    retryAfterMs: parseRetryAfter(response.headers.get('retry-after')),
  });
}

function createFetchError(error: unknown, timedOut: boolean) {
  if (timedOut) {
    return new ApiClientError({
      message: 'Превышено время ожидания ответа.',
      kind: 'timeout',
    });
  }

  if (isAbortError(error)) {
    return new ApiClientError({
      message: 'Запрос отменен.',
      kind: 'request_aborted',
    });
  }

  return new ApiClientError({
    message: 'Не удалось связаться с сервером.',
    kind: 'network_unavailable',
  });
}

function classifyHttpStatus(status: number): ApiErrorKind {
  if (status === 401 || status === 403) {
    return 'authentication';
  }
  if (status === 408) {
    return 'timeout';
  }
  if (status === 429) {
    return 'rate_limited';
  }
  if (status === 400 || status === 422) {
    return 'validation';
  }
  if (status >= 500) {
    return 'temporary_server_failure';
  }
  return 'permanent_server_failure';
}

function getDefaultTimeoutMs(method: string, body?: BodyInit | null) {
  if (body instanceof FormData) {
    return API_TIMEOUT_MS.upload;
  }
  return method === 'GET' ? API_TIMEOUT_MS.read : API_TIMEOUT_MS.mutation;
}

function isAbortError(error: unknown) {
  return error instanceof DOMException && error.name === 'AbortError';
}

function createTimeoutSignal(signal: AbortSignal | null | undefined, timeoutMs: number) {
  const controller = new AbortController();
  let timedOut = false;
  let finished = false;

  const abortFromExternalSignal = () => {
    if (!finished && !controller.signal.aborted) {
      controller.abort(signal?.reason);
    }
  };

  if (signal?.aborted) {
    abortFromExternalSignal();
  } else {
    signal?.addEventListener('abort', abortFromExternalSignal, { once: true });
  }

  const timeoutId = window.setTimeout(() => {
    timedOut = true;
    controller.abort();
  }, timeoutMs);

  return {
    signal: controller.signal,
    get timedOut() {
      return timedOut;
    },
    cleanup() {
      finished = true;
      window.clearTimeout(timeoutId);
      signal?.removeEventListener('abort', abortFromExternalSignal);
    },
  };
}

export function isRetryableReadRequest(method: string, path: string) {
  return method.toUpperCase() === 'GET' && isSafeReadPath(path);
}

export function isSafeReadPath(path: string) {
  const cleanPath = path.startsWith('/') ? path : `/${path}`;
  return [
    /^\/products$/,
    /^\/products\/suggestions$/,
    /^\/products\/\d+$/,
    /^\/products\/\d+\/reviews$/,
    /^\/categories$/,
    /^\/categories\/\d+$/,
    /^\/tags$/,
    /^\/banners$/,
    /^\/favorites$/,
    /^\/cart$/,
    /^\/orders$/,
    /^\/orders\/\d+$/,
    /^\/orders\/\d+\/payment$/,
    /^\/users\/me$/,
    /^\/users\/me\/personal-data$/,
    /^\/customer-notifications\/me\/subscription$/,
  ].some((pattern) => pattern.test(cleanPath));
}

export function shouldRetryError(error: unknown) {
  if (!(error instanceof ApiClientError)) {
    return false;
  }
  if (error.kind === 'network_unavailable' || error.kind === 'timeout') {
    return true;
  }
  return RETRYABLE_STATUSES.has(error.status);
}

async function waitForRetryDelay(error: unknown, attempt: number, signal?: AbortSignal | null) {
  const retryAfterMs = error instanceof ApiClientError ? error.retryAfterMs : undefined;
  const exponentialDelay = Math.min(
    RETRY_POLICY.maxDelayMs,
    RETRY_POLICY.baseDelayMs * 2 ** (attempt - 1),
  );
  const jitter = Math.floor(Math.random() * RETRY_POLICY.jitterMs);
  const delayMs = Math.max(retryAfterMs ?? 0, exponentialDelay + jitter);

  await new Promise<void>((resolve, reject) => {
    if (signal?.aborted) {
      reject(new ApiClientError({ message: 'Запрос отменен.', kind: 'request_aborted' }));
      return;
    }
    const cleanup = () => signal?.removeEventListener('abort', onAbort);
    const timer = window.setTimeout(() => {
      cleanup();
      resolve();
    }, delayMs);
    const onAbort = () => {
      window.clearTimeout(timer);
      cleanup();
      reject(new ApiClientError({ message: 'Запрос отменен.', kind: 'request_aborted' }));
    };
    signal?.addEventListener('abort', onAbort, { once: true });
  });
}

function parseRetryAfter(value: string | null) {
  if (!value) {
    return undefined;
  }
  const seconds = Number(value);
  if (Number.isFinite(seconds) && seconds >= 0) {
    return seconds * 1000;
  }
  const retryDate = Date.parse(value);
  if (Number.isFinite(retryDate)) {
    return Math.max(0, retryDate - Date.now());
  }
  return undefined;
}

function byteBucket(value: string | null): 'unknown' | '0' | '1kb' | '10kb' | '100kb' | '1mb' | 'large' {
  if (!value) {
    return 'unknown';
  }
  const bytes = Number(value);
  if (!Number.isFinite(bytes) || bytes < 0) {
    return 'unknown';
  }
  if (bytes === 0) {
    return '0';
  }
  if (bytes <= 1024) {
    return '1kb';
  }
  if (bytes <= 10 * 1024) {
    return '10kb';
  }
  if (bytes <= 100 * 1024) {
    return '100kb';
  }
  if (bytes <= 1024 * 1024) {
    return '1mb';
  }
  return 'large';
}

export function isUnauthorizedError(error: unknown) {
  return error instanceof ApiClientError && error.kind === 'authentication';
}

export function isRequestAbortedError(error: unknown) {
  return error instanceof ApiClientError && error.kind === 'request_aborted';
}

export function getApiErrorTelemetryCategory(error: unknown) {
  return error instanceof ApiClientError ? error.kind : 'unknown';
}

export function isTemporaryNetworkError(error: unknown) {
  return error instanceof ApiClientError
    && (
      error.kind === 'network_unavailable'
      || error.kind === 'timeout'
      || error.kind === 'rate_limited'
      || error.kind === 'temporary_server_failure'
    );
}

const TECHNICAL_MESSAGE_PATTERN =
  /\b(jwt|token|bearer|request|response|fetch|network|backend|api|unauthorized|forbidden|validation|internal|failed|error|dev)\b/i;

const KIND_ERROR_MESSAGES: Record<ApiErrorKind, string> = {
  authentication: 'Войдите через Telegram, чтобы продолжить.',
  validation: 'Проверьте данные и попробуйте снова.',
  network_unavailable: 'Связь с сервером пропала. Проверьте интернет и попробуйте снова.',
  timeout: 'Сервер отвечает слишком долго. Попробуйте еще раз.',
  request_aborted: 'Запрос отменен.',
  rate_limited: 'Слишком много действий. Попробуйте позже.',
  temporary_server_failure: 'Сервис временно недоступен. Попробуйте позже.',
  permanent_server_failure: 'Не удалось выполнить действие. Попробуйте снова.',
};

function isUserFacingRussianMessage(message: string) {
  return /[а-яё]/i.test(message) && !TECHNICAL_MESSAGE_PATTERN.test(message);
}

export function toApiErrorMessage(error: unknown) {
  if (error instanceof ApiClientError) {
    const baseMessage = isUserFacingRussianMessage(error.message)
      ? error.message
      : KIND_ERROR_MESSAGES[error.kind];
    return error.requestId ? `${baseMessage}\nКод обращения: ${error.requestId}` : baseMessage;
  }

  if (error instanceof Error) {
    return isUserFacingRussianMessage(error.message)
      ? error.message
      : 'Не удалось связаться с сервером. Проверьте интернет и попробуйте снова.';
  }

  return 'Что-то пошло не так';
}
