type TelemetryEventName =
  | 'mini_app.bootstrap_started'
  | 'mini_app.bootstrap_completed'
  | 'telegram.initialized'
  | 'auth.started'
  | 'auth.completed'
  | 'auth.failed'
  | 'route.rendered'
  | 'first_product_card.rendered'
  | 'first_key_image.loaded'
  | 'web_vital.lcp'
  | 'web_vital.inp'
  | 'web_vital.cls'
  | 'web_vital.ttfb'
  | 'web_vital.fcp'
  | 'api.request_completed'
  | 'api.request_failed'
  | 'api.retry_scheduled'
  | 'api.retry_exhausted'
  | 'network.state_changed'
  | 'checkout.started'
  | 'checkout.completed'
  | 'checkout.failed'
  | 'checkout.ambiguous_outcome'
  | 'payment.submit_started'
  | 'payment.submit_completed'
  | 'payment.submit_failed'
  | 'receipt.prepare_completed'
  | 'receipt.upload_completed'
  | 'receipt.upload_failed'
  | 'chunk.load_failed'
  | 'chunk.reload_attempted'
  | 'chunk.recovery_failed'
  | 'frontend.error_boundary_triggered';

export type TelemetryEventData = {
  route?: string;
  platform?: 'ios' | 'android' | 'web' | 'tdesktop' | 'unknown';
  telegram_webapp_version?: string;
  theme_mode?: 'light' | 'dark' | 'auto' | 'unknown';
  network_state?: 'online' | 'slow' | 'offline' | 'recovering' | 'unknown';
  connection_type?: 'slow-2g' | '2g' | '3g' | '4g' | 'unknown';
  save_data?: boolean;
  duration_ms?: number;
  value?: number;
  method?: string;
  endpoint_scope?: string;
  status?: number;
  retry_count?: number;
  error_category?:
    | 'authentication'
    | 'validation'
    | 'network_unavailable'
    | 'timeout'
    | 'request_aborted'
    | 'rate_limited'
    | 'temporary_server_failure'
    | 'permanent_server_failure'
    | 'chunk_load_failed'
    | 'render_error'
    | 'unknown';
  request_id?: string;
  app_version?: string;
  success?: boolean;
  response_size_bucket?: 'unknown' | '0' | '1kb' | '10kb' | '100kb' | '1mb' | 'large';
  payload_size_bucket?: 'unknown' | '0' | '1kb' | '10kb' | '100kb' | '1mb' | 'large';
  viewport_class?: 'small' | 'medium' | 'large' | 'unknown';
  device_class?: 'mobile' | 'tablet' | 'desktop' | 'unknown';
  idempotency_key_hash?: string;
};

type TelemetryEvent = TelemetryEventData & {
  name: TelemetryEventName;
  version: 1;
  session_id: string;
  client_event_id: string;
};

type TrackOptions = {
  priority?: 'normal' | 'critical';
};

const API_BASE_URL = normalizeApiBaseUrl(import.meta.env.VITE_API_BASE_URL);
const TELEMETRY_SESSION_STORAGE_KEY = 'telegram_shop_telemetry_session';
const TELEMETRY_SESSION_TTL_MS = 30 * 60 * 1000;
const MAX_QUEUE_EVENTS = 80;
const MAX_BATCH_EVENTS = 20;
const MAX_EVENT_BYTES = 4 * 1024;
const MAX_PAYLOAD_BYTES = 32 * 1024;
const FLUSH_DELAY_MS = 5_000;
const LOW_PRIORITY_EVENTS = new Set<TelemetryEventName>([
  'api.request_completed',
  'route.rendered',
  'network.state_changed',
  'web_vital.lcp',
  'web_vital.inp',
  'web_vital.cls',
  'web_vital.ttfb',
  'web_vital.fcp',
]);
const CRITICAL_EVENTS = new Set<TelemetryEventName>([
  'auth.failed',
  'api.request_failed',
  'api.retry_exhausted',
  'checkout.failed',
  'checkout.ambiguous_outcome',
  'payment.submit_failed',
  'receipt.upload_failed',
  'chunk.load_failed',
  'chunk.recovery_failed',
  'frontend.error_boundary_triggered',
]);

let queue: TelemetryEvent[] = [];
let flushTimer = 0;
let initialized = false;
let sentCounter = 0;

export function initTelemetryClient() {
  if (initialized || !isTelemetryEnabled()) {
    return;
  }
  initialized = true;
  window.addEventListener('pagehide', () => {
    void flushTelemetry({ preferBeacon: true });
  });
  window.setTimeout(() => {
    void import('./webVitals').then((module) => module.startWebVitalsTelemetry((name, value) => {
      trackTelemetry(name, {
        value,
        route: window.location.pathname,
        ...getConnectionTelemetry(),
        ...getViewportTelemetry(),
      });
    }));
  }, 0);
}

export function trackTelemetry(
  name: TelemetryEventName,
  data: TelemetryEventData = {},
  options: TrackOptions = {},
) {
  if (!isTelemetryEnabled() || !shouldSampleClientEvent(name, data)) {
    return;
  }
  const event = sanitizeTelemetryEvent({
    ...data,
    name,
    version: 1,
    session_id: getTelemetrySessionId(),
    client_event_id: createClientEventId(),
    app_version: data.app_version ?? __APP_VERSION__,
  });
  if (encodedBytes(event) > MAX_EVENT_BYTES) {
    return;
  }
  enqueueTelemetry(event, options.priority ?? (CRITICAL_EVENTS.has(name) ? 'critical' : 'normal'));
}

export async function flushTelemetry({ preferBeacon = false }: { preferBeacon?: boolean } = {}) {
  window.clearTimeout(flushTimer);
  flushTimer = 0;
  if (!queue.length) {
    return;
  }
  const batch = takeBatch();
  const payload = JSON.stringify({ events: batch });
  if (encodedBytes(payload) > MAX_PAYLOAD_BYTES) {
    return;
  }

  if (preferBeacon && navigator.sendBeacon) {
    const blob = new Blob([payload], { type: 'application/json' });
    if (navigator.sendBeacon(telemetryUrl(), blob)) {
      return;
    }
  }

  try {
    await fetch(telemetryUrl(), {
      method: 'POST',
      body: payload,
      headers: { 'Content-Type': 'application/json' },
      keepalive: payload.length <= MAX_PAYLOAD_BYTES,
    });
  } catch {
    // Best-effort only. Dropping this batch prevents a growing retry loop.
  }
}

export function sanitizeTelemetryEvent(event: TelemetryEvent): TelemetryEvent {
  return {
    name: event.name,
    version: 1,
    session_id: clamp(event.session_id, 64),
    client_event_id: clamp(event.client_event_id, 64),
    route: event.route ? normalizeRoute(event.route) : undefined,
    platform: event.platform,
    telegram_webapp_version: clampOptional(event.telegram_webapp_version, 32),
    theme_mode: event.theme_mode,
    network_state: event.network_state,
    connection_type: event.connection_type,
    save_data: event.save_data,
    duration_ms: finiteInteger(event.duration_ms, 0, 300_000),
    value: finiteNumber(event.value, 0, 10_000_000),
    method: clampOptional(event.method?.toUpperCase(), 10),
    endpoint_scope: event.endpoint_scope ? normalizeEndpointScope(event.endpoint_scope) : undefined,
    status: finiteInteger(event.status, 0, 599),
    retry_count: finiteInteger(event.retry_count, 0, 10),
    error_category: event.error_category,
    request_id: clampOptional(event.request_id, 64),
    app_version: clampOptional(event.app_version, 80),
    success: event.success,
    response_size_bucket: event.response_size_bucket,
    payload_size_bucket: event.payload_size_bucket,
    viewport_class: event.viewport_class,
    device_class: event.device_class,
    idempotency_key_hash: clampOptional(event.idempotency_key_hash, 24),
  };
}

export function normalizeEndpointScope(value: string) {
  const path = stripApiPrefix(stripUrlParts(value));
  return path
    .split('/')
    .map((part) => (/^\d+$/.test(part) || isUuidLike(part) ? ':id' : part))
    .join('/') || '/';
}

export function normalizeRoute(value: string) {
  return stripUrlParts(value)
    .split('/')
    .map((part) => (/^\d+$/.test(part) || isUuidLike(part) ? ':id' : part))
    .join('/') || '/';
}

export async function hashCorrelationKey(value: string) {
  const bytes = new TextEncoder().encode(value);
  if (crypto.subtle) {
    const digest = await crypto.subtle.digest('SHA-256', bytes);
    return Array.from(new Uint8Array(digest))
      .slice(0, 8)
      .map((byte) => byte.toString(16).padStart(2, '0'))
      .join('');
  }
  return String(Math.abs(simpleHash(value))).slice(0, 16);
}

export function getConnectionTelemetry() {
  const connection = (navigator as Navigator & {
    connection?: { effectiveType?: string; saveData?: boolean };
  }).connection;
  return {
    connection_type: normalizeConnectionType(connection?.effectiveType),
    save_data: Boolean(connection?.saveData),
  };
}

export function getViewportTelemetry(): Pick<TelemetryEventData, 'viewport_class' | 'device_class'> {
  const width = window.innerWidth;
  return {
    viewport_class: width < 380 ? 'small' : width < 768 ? 'medium' : 'large',
    device_class: width < 768 ? 'mobile' : width < 1024 ? 'tablet' : 'desktop',
  };
}

function enqueueTelemetry(event: TelemetryEvent, priority: 'normal' | 'critical') {
  if (queue.length >= MAX_QUEUE_EVENTS) {
    const dropIndex = priority === 'critical'
      ? queue.findIndex((queued) => LOW_PRIORITY_EVENTS.has(queued.name))
      : 0;
    queue.splice(dropIndex >= 0 ? dropIndex : 0, 1);
  }
  queue.push(event);
  if (queue.length >= MAX_BATCH_EVENTS) {
    void flushTelemetry();
  } else if (!flushTimer) {
    flushTimer = window.setTimeout(() => void flushTelemetry(), FLUSH_DELAY_MS);
  }
}

function takeBatch() {
  const batch = queue.slice(0, MAX_BATCH_EVENTS);
  queue = queue.slice(batch.length);
  return batch;
}

function shouldSampleClientEvent(name: TelemetryEventName, data: TelemetryEventData) {
  if (CRITICAL_EVENTS.has(name)) {
    return true;
  }
  if (name === 'api.request_completed' && data.method === 'GET') {
    return deterministicSample(name, data.endpoint_scope ?? '', 0.2);
  }
  if (LOW_PRIORITY_EVENTS.has(name)) {
    return deterministicSample(name, data.route ?? data.endpoint_scope ?? '', 0.5);
  }
  return true;
}

function deterministicSample(...args: [string, string, number]) {
  const [name, scope, rate] = args;
  const hash = Math.abs(simpleHash(`${getTelemetrySessionId()}:${name}:${scope}`));
  return (hash % 10_000) / 10_000 <= rate;
}

function telemetryUrl() {
  return buildTelemetryUrl(API_BASE_URL);
}

function getTelemetrySessionId() {
  const now = Date.now();
  try {
    const current = window.sessionStorage.getItem(TELEMETRY_SESSION_STORAGE_KEY);
    if (current) {
      const parsed = JSON.parse(current) as { id?: string; createdAt?: number };
      if (
        parsed.id
        && parsed.createdAt
        && now - parsed.createdAt < TELEMETRY_SESSION_TTL_MS
      ) {
        return parsed.id;
      }
    }
    const id = createRandomId();
    window.sessionStorage.setItem(
      TELEMETRY_SESSION_STORAGE_KEY,
      JSON.stringify({ id, createdAt: now }),
    );
    return id;
  } catch {
    return createRandomId();
  }
}

function createClientEventId() {
  sentCounter += 1;
  return `${Date.now().toString(36)}-${sentCounter.toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
}

function createRandomId() {
  if (crypto.randomUUID) {
    return crypto.randomUUID();
  }
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`;
}

function stripUrlParts(value: string) {
  try {
    const url = value.startsWith('http') ? new URL(value) : new URL(value, window.location.origin);
    return url.pathname || '/';
  } catch {
    return value.split(/[?#]/, 1)[0] || '/';
  }
}

function stripApiPrefix(path: string) {
  return path.replace(/^\/api\/v\d+(?=\/|$)/, '') || '/';
}

function isUuidLike(value: string) {
  return /^[0-9a-f]{8}-[0-9a-f-]{13,}$/i.test(value);
}

function normalizeConnectionType(value?: string): NonNullable<TelemetryEventData['connection_type']> {
  return value === 'slow-2g' || value === '2g' || value === '3g' || value === '4g'
    ? value
    : 'unknown';
}

function finiteInteger(value: number | undefined, min: number, max: number) {
  if (!Number.isFinite(value)) {
    return undefined;
  }
  return Math.min(Math.max(Math.trunc(value as number), min), max);
}

function finiteNumber(value: number | undefined, min: number, max: number) {
  if (!Number.isFinite(value)) {
    return undefined;
  }
  return Math.min(Math.max(value as number, min), max);
}

function clamp(value: string, maxLength: number) {
  return value.slice(0, maxLength);
}

function clampOptional(value: string | undefined, maxLength: number) {
  return value ? clamp(value, maxLength) : undefined;
}

function encodedBytes(value: unknown) {
  return new TextEncoder().encode(typeof value === 'string' ? value : JSON.stringify(value)).length;
}

function simpleHash(value: string) {
  let hash = 0;
  for (let index = 0; index < value.length; index += 1) {
    hash = Math.imul(31, hash) + value.charCodeAt(index) | 0;
  }
  return hash;
}

function isTelemetryEnabled() {
  return import.meta.env.VITE_TELEMETRY_DISABLED !== 'true';
}
import { buildTelemetryUrl, normalizeApiBaseUrl } from '../utils/urls';
