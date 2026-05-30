import { getStoredToken } from '../auth/tokenStorage';
import type {
  AnalyticsEvent,
  AnalyticsSummary,
  Banner,
  BannerPayload,
  Category,
  Order,
  OrderStatus,
  PageList,
  Product,
  ProductCreate,
  ProductStatus,
  ProductUpdate,
  ProductVariant,
  ProductVariantPayload,
  PromoCode,
  PromoCodePayload,
  Review,
  ReviewStatus,
  Tag,
  UploadedBannerImage,
  UploadedProductImage,
  User,
} from './types';

export const API_BASE_URL = (
  (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? 'http://localhost:8000/api/v1'
).replace(/\/+$/, '');

export function resolveMediaUrl(url: string | null | undefined): string {
  if (!url) {
    return '';
  }

  if (/^(https?:)?\/\//.test(url) || url.startsWith('data:')) {
    return url;
  }

  const origin = new URL(API_BASE_URL).origin;
  return `${origin}${url.startsWith('/') ? url : `/${url}`}`;
}

type QueryValue = string | number | boolean | null | undefined;
type QueryParams = Record<string, QueryValue>;

interface RequestOptions {
  method?: 'GET' | 'POST' | 'PATCH' | 'DELETE';
  query?: QueryParams;
  body?: unknown;
  formData?: FormData;
}

export class ApiError extends Error {
  status: number;
  details: unknown;

  constructor(message: string, status: number, details: unknown) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.details = details;
  }
}

function buildUrl(path: string, query?: QueryParams): string {
  const url = new URL(`${API_BASE_URL}${path.startsWith('/') ? path : `/${path}`}`);

  Object.entries(query ?? {}).forEach(([key, value]) => {
    if (value === undefined || value === null || value === '') {
      return;
    }

    url.searchParams.set(key, String(value));
  });

  return url.toString();
}

function getErrorMessage(payload: unknown, fallback: string): string {
  if (!payload || typeof payload !== 'object') {
    return fallback;
  }

  const detail = 'detail' in payload ? (payload as { detail?: unknown }).detail : undefined;
  if (typeof detail === 'string') {
    return detail;
  }

  if (Array.isArray(detail)) {
    return detail
      .map((item) => {
        if (item && typeof item === 'object' && 'msg' in item) {
          const loc = 'loc' in item && Array.isArray(item.loc) ? `${item.loc.join('.')}: ` : '';
          return `${loc}${String(item.msg)}`;
        }
        return JSON.stringify(item);
      })
      .join('; ');
  }

  if ('message' in payload && typeof (payload as { message?: unknown }).message === 'string') {
    return String((payload as { message: string }).message);
  }

  return fallback;
}

export async function apiRequest<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const headers = new Headers();
  const token = getStoredToken();

  if (token) {
    headers.set('Authorization', `Bearer ${token}`);
  }

  let body: BodyInit | undefined;

  if (options.formData) {
    body = options.formData;
  } else if (options.body !== undefined) {
    headers.set('Content-Type', 'application/json');
    body = JSON.stringify(options.body);
  }

  const response = await fetch(buildUrl(path, options.query), {
    method: options.method ?? 'GET',
    headers,
    body,
  });

  const rawText = await response.text();
  const payload = rawText ? safeJson(rawText) : undefined;

  if (!response.ok) {
    throw new ApiError(
      getErrorMessage(payload, `${response.status} ${response.statusText}`),
      response.status,
      payload,
    );
  }

  return payload as T;
}

function safeJson(rawText: string): unknown {
  try {
    return JSON.parse(rawText);
  } catch {
    return rawText;
  }
}

export const api = {
  users: {
    me: () => apiRequest<User>('/users/me'),
  },
  categories: {
    list: () => apiRequest<Category[]>('/categories'),
  },
  tags: {
    list: () => apiRequest<Tag[]>('/tags'),
  },
  products: {
    listAdmin: (query: QueryParams = {}) =>
      apiRequest<PageList<Product>>('/products/admin', { query }),
    getAdmin: (productId: number) => apiRequest<Product>(`/products/admin/${productId}`),
    create: (body: ProductCreate) => apiRequest<Product>('/products', { method: 'POST', body }),
    update: (productId: number, body: ProductUpdate) =>
      apiRequest<Product>(`/products/${productId}`, { method: 'PATCH', body }),
    updateStatus: (productId: number, status: ProductStatus) =>
      apiRequest<Product>(`/products/${productId}/status`, {
        method: 'PATCH',
        body: { status },
      }),
    archive: (productId: number) =>
      apiRequest<Product>(`/products/${productId}/archive`, { method: 'PATCH' }),
    createVariant: (productId: number, body: ProductVariantPayload) =>
      apiRequest<ProductVariant>(`/products/${productId}/variants`, { method: 'POST', body }),
    updateVariant: (variantId: number, body: Partial<ProductVariantPayload>) =>
      apiRequest<ProductVariant>(`/products/variants/${variantId}`, { method: 'PATCH', body }),
    deleteVariant: (variantId: number) =>
      apiRequest<void>(`/products/variants/${variantId}`, { method: 'DELETE' }),
    uploadImage: (
      productId: number,
      file: File,
      options: { altText?: string; position?: number; isPrimary?: boolean } = {},
    ) => {
      const formData = new FormData();
      formData.append('file', file);
      if (options.altText) {
        formData.append('alt_text', options.altText);
      }
      if (options.position !== undefined) {
        formData.append('position', String(options.position));
      }
      formData.append('is_primary', String(options.isPrimary ?? false));
      return apiRequest<UploadedProductImage>(`/uploads/products/${productId}/images`, {
        method: 'POST',
        formData,
      });
    },
  },
  orders: {
    listAdmin: (query: QueryParams = {}) => apiRequest<PageList<Order>>('/orders/admin', { query }),
    getAdmin: (orderId: number) => apiRequest<Order>(`/orders/admin/${orderId}`),
    updateStatus: (orderId: number, status: OrderStatus) =>
      apiRequest<Order>(`/orders/admin/${orderId}/status`, {
        method: 'PATCH',
        body: { status },
      }),
  },
  banners: {
    listAdmin: (query: QueryParams = {}) =>
      apiRequest<PageList<Banner>>('/banners/admin', { query }),
    create: (body: BannerPayload) =>
      apiRequest<Banner>('/banners/admin', { method: 'POST', body }),
    update: (bannerId: number, body: Partial<BannerPayload>) =>
      apiRequest<Banner>(`/banners/admin/${bannerId}`, { method: 'PATCH', body }),
    activate: (bannerId: number) =>
      apiRequest<Banner>(`/banners/admin/${bannerId}/activate`, { method: 'PATCH' }),
    deactivate: (bannerId: number) =>
      apiRequest<Banner>(`/banners/admin/${bannerId}/deactivate`, { method: 'PATCH' }),
    uploadImage: (file: File, altText?: string) => {
      const formData = new FormData();
      formData.append('file', file);
      if (altText) {
        formData.append('alt_text', altText);
      }
      return apiRequest<UploadedBannerImage>('/uploads/banners/images', {
        method: 'POST',
        formData,
      });
    },
  },
  promoCodes: {
    list: (query: QueryParams = {}) => apiRequest<PageList<PromoCode>>('/promo-codes', { query }),
    create: (body: PromoCodePayload) =>
      apiRequest<PromoCode>('/promo-codes', { method: 'POST', body }),
    update: (promoCodeId: number, body: Partial<PromoCodePayload>) =>
      apiRequest<PromoCode>(`/promo-codes/${promoCodeId}`, { method: 'PATCH', body }),
    deactivate: (promoCodeId: number) =>
      apiRequest<void>(`/promo-codes/${promoCodeId}`, { method: 'DELETE' }),
  },
  reviews: {
    listAdmin: (status?: ReviewStatus) =>
      apiRequest<PageList<Review> | { items: Review[] }>('/reviews/admin', {
        query: { status },
      }),
    approve: (reviewId: number) =>
      apiRequest<Review>(`/reviews/admin/${reviewId}/approve`, { method: 'PATCH' }),
    reject: (reviewId: number) =>
      apiRequest<Review>(`/reviews/admin/${reviewId}/reject`, { method: 'PATCH' }),
  },
  analytics: {
    summary: (query: QueryParams = {}) =>
      apiRequest<AnalyticsSummary>('/analytics/summary', { query }),
    events: (query: QueryParams = {}) =>
      apiRequest<PageList<AnalyticsEvent>>('/analytics/events', { query }),
  },
};
