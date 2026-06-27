import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  addCartItem,
  addFavorite,
} from './index';
import {
  ApiClientError,
  apiRequest,
  clearStoredAccessToken,
  getStoredAccessToken,
  storeAccessToken,
  toApiErrorMessage,
} from './client';
import { shouldClearStoredTokenAfterAuthError } from '../auth/sessionPolicy';
import { getNetworkState, setNetworkState } from '../network/networkState';
import { flushTelemetry } from '../telemetry';

function jsonResponse(payload: unknown, status = 200, headers: Record<string, string> = {}) {
  return new Response(JSON.stringify(payload), {
    status,
    headers: {
      'content-type': 'application/json',
      ...headers,
    },
  });
}

function abortableNeverFetch() {
  return vi.fn((_url: RequestInfo | URL, init?: RequestInit) => (
    new Promise<Response>((_resolve, reject) => {
      init?.signal?.addEventListener('abort', () => {
        reject(new DOMException('Aborted', 'AbortError'));
      });
    })
  ));
}

describe('apiRequest resilience', () => {
  beforeEach(() => {
    window.localStorage.clear();
    vi.spyOn(Math, 'random').mockReturnValue(0);
  });

  afterEach(() => {
    clearStoredAccessToken();
    setNetworkState('online');
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
    vi.useRealTimers();
  });

  it('retries a safe GET after a temporary 503', async () => {
    vi.useFakeTimers();
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(jsonResponse({ detail: 'temporary' }, 503))
      .mockResolvedValueOnce(jsonResponse({ items: [] }));
    vi.stubGlobal('fetch', fetchMock);

    const request = apiRequest('/products');
    await Promise.resolve();
    expect(fetchMock).toHaveBeenCalledTimes(1);

    await vi.advanceTimersByTimeAsync(350);

    await expect(request).resolves.toEqual({ items: [] });
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it.each([401, 403, 422])('does not retry GET after HTTP %i', async (status) => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ detail: 'stop' }, status));
    vi.stubGlobal('fetch', fetchMock);

    await expect(apiRequest('/products')).rejects.toMatchObject({ status });
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it('keeps JWT after timeout and does not classify it as an auth reset', async () => {
    vi.useFakeTimers();
    storeAccessToken('jwt-for-test');
    vi.stubGlobal('fetch', abortableNeverFetch());

    const request = apiRequest('/products', { retry: false, timeoutMs: 100 })
      .catch((error: unknown) => error);
    await vi.advanceTimersByTimeAsync(100);

    const capturedError = await request;

    expect(capturedError).toMatchObject({ kind: 'timeout' });
    expect(getStoredAccessToken()).toBe('jwt-for-test');
    expect(shouldClearStoredTokenAfterAuthError(capturedError)).toBe(false);
  });

  it('does not display aborted requests as server errors', async () => {
    const controller = new AbortController();
    vi.stubGlobal('fetch', abortableNeverFetch());

    const request = apiRequest('/products/suggestions', {
      dedupe: false,
      query: { query: 'old', limit: 8 },
      retry: false,
      signal: controller.signal,
    }).catch((error: unknown) => error);
    controller.abort();

    await expect(request).resolves.toMatchObject({ kind: 'request_aborted' });
  });

  it('supports aborting an old search request when a new query starts', async () => {
    const oldController = new AbortController();
    const newController = new AbortController();
    const fetchMock = vi.fn((url: RequestInfo | URL, init?: RequestInit) => {
      if (String(url).includes('query=old')) {
        return new Promise<Response>((_resolve, reject) => {
          init?.signal?.addEventListener('abort', () => {
            reject(new DOMException('Aborted', 'AbortError'));
          });
        });
      }
      return Promise.resolve(jsonResponse({ items: [{ product_id: 1, name: 'New' }] }));
    });
    vi.stubGlobal('fetch', fetchMock);

    const oldRequest = apiRequest('/products/suggestions', {
      dedupe: false,
      query: { query: 'old', limit: 8 },
      retry: false,
      signal: oldController.signal,
    }).catch((error: unknown) => error);
    oldController.abort();
    const newRequest = apiRequest('/products/suggestions', {
      dedupe: false,
      query: { query: 'new', limit: 8 },
      retry: false,
      signal: newController.signal,
    });

    await expect(oldRequest).resolves.toMatchObject({ kind: 'request_aborted' });
    await expect(newRequest).resolves.toEqual({ items: [{ product_id: 1, name: 'New' }] });
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it('deduplicates simultaneous safe GET requests', async () => {
    let resolveFetch: (value: Response) => void = () => undefined;
    const fetchMock = vi.fn(() => (
      new Promise<Response>((resolve) => {
        resolveFetch = resolve;
      })
    ));
    vi.stubGlobal('fetch', fetchMock);

    const first = apiRequest('/cart');
    const second = apiRequest('/cart');

    expect(fetchMock).toHaveBeenCalledTimes(1);
    resolveFetch(jsonResponse({ quantity_total: 1 }));
    await expect(Promise.all([first, second])).resolves.toEqual([
      { quantity_total: 1 },
      { quantity_total: 1 },
    ]);
  });

  it('preserves backend request ID in normalized errors', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({ detail: 'temporary' }, 503, { 'x-request-id': 'req-123' }),
    );
    vi.stubGlobal('fetch', fetchMock);

    let capturedError: unknown;
    try {
      await apiRequest('/products', { retry: false });
    } catch (error) {
      capturedError = error;
    }

    expect(capturedError).toBeInstanceOf(ApiClientError);
    expect(capturedError).toMatchObject({ requestId: 'req-123' });
    expect(toApiErrorMessage(capturedError)).toContain('req-123');
  });

  it('captures normalized API failure telemetry without using retry transport', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(jsonResponse({ detail: 'temporary' }, 503, { 'x-request-id': 'req-telemetry' }))
      .mockResolvedValueOnce(new Response(null, { status: 202 }));
    vi.stubGlobal('fetch', fetchMock);

    await expect(apiRequest('/products/123', { retry: false })).rejects.toMatchObject({
      requestId: 'req-telemetry',
      kind: 'temporary_server_failure',
    });
    await flushTelemetry();

    expect(fetchMock).toHaveBeenCalledTimes(2);
    const telemetryPayload = JSON.parse(String(fetchMock.mock.calls[1][1]?.body));
    const telemetryEvent = telemetryPayload.events.find(
      (event: { request_id?: string }) => event.request_id === 'req-telemetry',
    );
    expect(telemetryEvent).toMatchObject({
      name: 'api.request_failed',
      endpoint_scope: '/products/:id',
      status: 503,
      retry_count: 0,
      request_id: 'req-telemetry',
      error_category: 'temporary_server_failure',
    });
  });

  it('keeps successful favorite and cart mutations local to the screen', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(jsonResponse({ id: 1, user_id: 1, product_id: 10 }))
      .mockResolvedValueOnce(jsonResponse({ id: 1, user_id: 1, items: [], total: '0.00' }));
    vi.stubGlobal('fetch', fetchMock);
    setNetworkState('online');

    await addFavorite(10);
    await addCartItem(10, 100);

    expect(getNetworkState()).toBe('online');
  });

  it('does not show the global network banner for local mutation failures', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ detail: 'temporary' }, 503));
    vi.stubGlobal('fetch', fetchMock);
    setNetworkState('online');

    await expect(addCartItem(10, 100)).rejects.toMatchObject({
      kind: 'temporary_server_failure',
    });

    expect(getNetworkState()).toBe('online');
  });

  it('clears JWT only for confirmed authentication errors', () => {
    expect(shouldClearStoredTokenAfterAuthError(
      new ApiClientError({ kind: 'authentication', message: 'auth', status: 401 }),
    )).toBe(true);
    expect(shouldClearStoredTokenAfterAuthError(
      new ApiClientError({ kind: 'temporary_server_failure', message: 'server', status: 500 }),
    )).toBe(false);
    expect(shouldClearStoredTokenAfterAuthError(
      new ApiClientError({ kind: 'timeout', message: 'timeout' }),
    )).toBe(false);
  });
});
