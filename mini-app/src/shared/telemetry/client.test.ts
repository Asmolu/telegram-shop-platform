import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

async function loadTelemetry() {
  vi.resetModules();
  return import('./client');
}

describe('telemetry client', () => {
  beforeEach(() => {
    window.sessionStorage.clear();
    vi.useFakeTimers();
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(null, { status: 202 })));
    Object.defineProperty(navigator, 'sendBeacon', {
      configurable: true,
      value: vi.fn().mockReturnValue(true),
    });
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it('flushes a bounded batch through fetch keepalive', async () => {
    const { flushTelemetry, trackTelemetry } = await loadTelemetry();

    trackTelemetry('checkout.failed', { endpoint_scope: '/orders/checkout' });
    trackTelemetry('api.retry_exhausted', { endpoint_scope: '/products', method: 'GET' });
    await flushTelemetry();

    expect(fetch).toHaveBeenCalledTimes(1);
    const [, init] = vi.mocked(fetch).mock.calls[0];
    expect(init?.keepalive).toBe(true);
    const payload = JSON.parse(String(init?.body));
    expect(payload.events).toHaveLength(2);
    expect(payload.events[0]).not.toHaveProperty('initData');
  });

  it('uses sendBeacon for page-hide flush when available', async () => {
    const { flushTelemetry, trackTelemetry } = await loadTelemetry();

    trackTelemetry('chunk.recovery_failed', { error_category: 'chunk_load_failed' });
    await flushTelemetry({ preferBeacon: true });

    expect(navigator.sendBeacon).toHaveBeenCalledTimes(1);
    expect(fetch).not.toHaveBeenCalled();
  });

  it('drops telemetry failures without changing network state', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('offline')));
    const { getNetworkState } = await import('../network/networkState');
    const { flushTelemetry, trackTelemetry } = await loadTelemetry();

    trackTelemetry('checkout.failed', { endpoint_scope: '/orders/checkout' });
    await expect(flushTelemetry()).resolves.toBeUndefined();

    expect(getNetworkState()).toBe('online');
  });

  it('normalizes routes and endpoint IDs while removing query strings', async () => {
    const { normalizeEndpointScope, normalizeRoute } = await loadTelemetry();

    expect(normalizeEndpointScope('/products/123?search=secret')).toBe('/products/:id');
    expect(normalizeEndpointScope('/orders/42/payment/receipt')).toBe('/orders/:id/payment/receipt');
    expect(normalizeRoute('/product/123?from=search')).toBe('/product/:id');
  });

  it('sanitizes forbidden and unknown fields before queueing', async () => {
    const { sanitizeTelemetryEvent } = await loadTelemetry();

    const sanitized = sanitizeTelemetryEvent({
      name: 'api.request_failed',
      version: 1,
      session_id: 'session-1234567890',
      client_event_id: 'event-1234567890',
      endpoint_scope: '/products/123?query=secret',
      request_id: 'r'.repeat(100),
      initData: 'secret',
      Authorization: 'Bearer secret',
      user_id: 7,
    } as never);

    expect(sanitized.endpoint_scope).toBe('/products/:id');
    expect(sanitized.request_id).toHaveLength(64);
    expect(sanitized).not.toHaveProperty('initData');
    expect(sanitized).not.toHaveProperty('Authorization');
    expect(sanitized).not.toHaveProperty('user_id');
  });

  it('evicts old low-priority events when the queue overflows', async () => {
    const { flushTelemetry, trackTelemetry } = await loadTelemetry();

    for (let index = 0; index < 90; index += 1) {
      trackTelemetry('checkout.failed', { endpoint_scope: '/orders/checkout' });
    }
    await flushTelemetry();

    const [, init] = vi.mocked(fetch).mock.calls[0];
    const payload = JSON.parse(String(init?.body));
    expect(payload.events).toHaveLength(20);
  });
});
