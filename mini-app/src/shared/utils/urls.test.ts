import { describe, expect, it } from 'vitest';
import {
  buildApiUrl,
  buildTelemetryUrl,
  normalizeApiBaseUrl,
  resolvePublicMediaUrl,
} from './urls';

describe('frontend URL configuration', () => {
  it('supports absolute API base URLs without duplicate api prefixes', () => {
    expect(normalizeApiBaseUrl('https://api.stylexac.ru/api/v1/')).toBe(
      'https://api.stylexac.ru/api/v1',
    );
    expect(buildApiUrl('https://api.stylexac.ru/api/v1/', '/products')).toBe(
      'https://api.stylexac.ru/api/v1/products',
    );
    expect(buildApiUrl('https://api.stylexac.ru/api/v1', '/api/v1/products')).toBe(
      'https://api.stylexac.ru/api/v1/products',
    );
  });

  it('supports relative and empty API base URLs', () => {
    expect(normalizeApiBaseUrl('/api/v1/')).toBe('/api/v1');
    expect(normalizeApiBaseUrl('')).toBe('/api/v1');
    expect(buildApiUrl('/api/v1/', '/products', { limit: 20 })).toBe(
      'http://localhost:3000/api/v1/products?limit=20',
    );
    expect(buildApiUrl('', 'api/v1/categories')).toBe(
      'http://localhost:3000/api/v1/categories',
    );
  });

  it('rejects invalid API base protocols', () => {
    expect(() => normalizeApiBaseUrl('ftp://api.stylexac.ru/api/v1')).toThrow(
      'VITE_API_BASE_URL',
    );
    expect(() => normalizeApiBaseUrl('//api.stylexac.ru/api/v1')).toThrow(
      'VITE_API_BASE_URL',
    );
  });

  it('resolves upload URLs for absolute and same-origin modes', () => {
    expect(resolvePublicMediaUrl('/uploads/products/card.webp', '/api/v1')).toBe(
      '/uploads/products/card.webp',
    );
    expect(resolvePublicMediaUrl('products/card.webp', '/api/v1')).toBe(
      '/uploads/products/card.webp',
    );
    expect(resolvePublicMediaUrl('/uploads/products/card.webp', 'https://api.stylexac.ru/api/v1'))
      .toBe('https://api.stylexac.ru/uploads/products/card.webp');
    expect(resolvePublicMediaUrl('https://cdn.example.test/image.webp', '/api/v1')).toBe(
      'https://cdn.example.test/image.webp',
    );
  });

  it('builds telemetry endpoints for relative and absolute modes', () => {
    expect(buildTelemetryUrl('/api/v1')).toBe('/api/v1/analytics/telemetry');
    expect(buildTelemetryUrl('https://api.stylexac.ru/api/v1/')).toBe(
      'https://api.stylexac.ru/api/v1/analytics/telemetry',
    );
  });
});
