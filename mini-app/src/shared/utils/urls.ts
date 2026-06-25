const DEFAULT_API_BASE_URL = '/api/v1';
const API_PREFIX_PATTERN = /(?:\/api\/v1)+$/;

export function normalizeApiBaseUrl(value?: string | null) {
  const raw = value?.trim() ?? '';
  if (!raw) {
    return DEFAULT_API_BASE_URL;
  }

  if (raw.startsWith('//') || (/^[a-z][a-z0-9+.-]*:\/\//i.test(raw) && !/^https?:\/\//i.test(raw))) {
    throw new Error('VITE_API_BASE_URL must be an absolute http(s) URL or a relative path');
  }

  if (/^https?:\/\//i.test(raw)) {
    const url = new URL(raw);
    url.hash = '';
    url.search = '';
    url.pathname = normalizeApiPath(url.pathname);
    return url.toString().replace(/\/+$/, '');
  }

  return normalizeApiPath(raw);
}

export function buildApiUrl(
  baseUrl: string,
  path: string,
  query?: Record<string, string | number | boolean | null | undefined>,
) {
  const normalizedBase = normalizeApiBaseUrl(baseUrl);
  const cleanPath = stripDuplicateApiPrefix(path);
  const url = /^https?:\/\//i.test(normalizedBase)
    ? new URL(joinUrlPath(normalizedBase, cleanPath))
    : new URL(joinUrlPath(normalizedBase, cleanPath), window.location.origin);

  Object.entries(query ?? {}).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') {
      url.searchParams.set(key, String(value));
    }
  });

  return url.toString();
}

export function getApiOriginFromBase(baseUrl: string) {
  const normalizedBase = normalizeApiBaseUrl(baseUrl);
  if (!/^https?:\/\//i.test(normalizedBase)) {
    return window.location.origin;
  }
  return new URL(normalizedBase).origin;
}

export function resolvePublicMediaUrl(
  url: string | null | undefined,
  baseUrl: string,
): string {
  if (!url) {
    return '';
  }

  if (/^(https?:)?\/\//i.test(url) || url.startsWith('data:') || url.startsWith('blob:')) {
    return url;
  }

  const cleanPath = url.startsWith('/') ? url : `/uploads/${url.replace(/^uploads\//, '')}`;
  const normalizedBase = normalizeApiBaseUrl(baseUrl);
  if (!/^https?:\/\//i.test(normalizedBase)) {
    return cleanPath;
  }
  return `${new URL(normalizedBase).origin}${cleanPath}`;
}

export function buildTelemetryUrl(baseUrl: string) {
  return joinUrlPath(normalizeApiBaseUrl(baseUrl), '/analytics/telemetry');
}

function normalizeApiPath(value: string) {
  const stripped = value.trim().replace(/^\/+/, '').replace(/\/+$/, '');
  if (!stripped) {
    return DEFAULT_API_BASE_URL;
  }
  return `/${stripped}`.replace(API_PREFIX_PATTERN, DEFAULT_API_BASE_URL);
}

function stripDuplicateApiPrefix(path: string) {
  const cleanPath = path.startsWith('/') ? path : `/${path}`;
  return cleanPath === DEFAULT_API_BASE_URL || cleanPath.startsWith(`${DEFAULT_API_BASE_URL}/`)
    ? cleanPath.slice(DEFAULT_API_BASE_URL.length) || '/'
    : cleanPath;
}

function joinUrlPath(baseUrl: string, path: string) {
  const cleanBase = baseUrl.replace(/\/+$/, '');
  const cleanPath = path.startsWith('/') ? path : `/${path}`;
  return `${cleanBase}${cleanPath}`;
}
