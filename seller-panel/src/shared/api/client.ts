import { getStoredToken } from '../auth/tokenStorage';
import { buildApiUrl, normalizeApiBaseUrl, resolvePublicMediaUrl } from '../utils/urls';
import type {
  AnalyticsEvent,
  AnalyticsSummary,
  Banner,
  BannerImageKind,
  BannerPayload,
  BroadcastCampaign,
  BroadcastCampaignDetail,
  BroadcastCampaignPayload,
  BroadcastCampaignPreview,
  BroadcastCampaignProcessBatchResponse,
  BroadcastCampaignTestResponse,
  BroadcastDelivery,
  BroadcastDeliverySummary,
  Category,
  CategoryPayload,
  ChannelEntryConfig,
  ChannelEntryPreview,
  ChannelEntryPreviewPayload,
  ChannelEntryPublishPayload,
  ChannelEntryPublishResponse,
  CustomerNotificationSubscription,
  CustomerOrderMessageResponse,
  DashboardSummary,
  Look,
  LookCreatePayload,
  LookStatus,
  LookUpdatePayload,
  ManualPayment,
  ManualPaymentStatus,
  NotificationTemplate,
  NotificationTemplatePayload,
  Notification,
  Order,
  OrderStatus,
  PageList,
  Product,
  ProductCreate,
  ProductSlugList,
  ProductStatus,
  ProductUpdate,
  ProductVariant,
  ProductVariantPayload,
  ProductVariantSkuList,
  PromoCode,
  PromoCodePayload,
  ReturnDecisionPayload,
  ReturnLifecyclePayload,
  ReturnRequest,
  ReturnRequestStatus,
  Review,
  ReviewStatus,
  SellerPaymentSettings,
  SellerPaymentSettingsPayload,
  SellerBotActionResponse,
  SellerBotStatus,
  SellerRegistrationResendCodeResponse,
  SellerRegistrationStartResponse,
  Tag,
  TagPayload,
  TelegramChannel,
  TelegramChannelCheckResponse,
  TelegramChannelEntryMessage,
  TelegramChannelPayload,
  TokenResponse,
  UploadedBannerImage,
  UploadedCategoryImage,
  UploadedLookImage,
  UploadedProductImage,
  UploadedTagImage,
  User,
} from './types';

export const API_BASE_URL = (
  normalizeApiBaseUrl(import.meta.env.VITE_API_BASE_URL as string | undefined)
);

export function resolveMediaUrl(url: string | null | undefined): string {
  if (!url) {
    return '';
  }

  return resolvePublicMediaUrl(url, API_BASE_URL);
}

type QueryValue = string | number | boolean | null | undefined;
type QueryParams = Record<string, QueryValue>;

interface RequestOptions {
  method?: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE';
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
  return buildApiUrl(API_BASE_URL, path, query);
}

function clampQueryLimit(query: QueryParams, maxLimit: number): QueryParams {
  const requestedLimit = Number(query.limit);
  if (!Number.isFinite(requestedLimit) || requestedLimit <= maxLimit) {
    return query;
  }

  return { ...query, limit: maxLimit };
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

  let response: Response;
  try {
    response = await fetch(buildUrl(path, options.query), {
      method: options.method ?? 'GET',
      headers,
      body,
    });
  } catch (error) {
    throw new ApiError('Network request failed', 0, {
      cause: error instanceof Error ? error.message : String(error),
    });
  }

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
  sellerAuth: {
    startRegistration: (body: {
      email: string;
      password: string;
      telegram_username: string;
    }) =>
      apiRequest<SellerRegistrationStartResponse>('/seller-auth/register/start', {
        method: 'POST',
        body,
      }),
    confirmRegistration: (body: { registration_id: number; code: string }) =>
      apiRequest<TokenResponse>('/seller-auth/register/confirm', { method: 'POST', body }),
    resendCode: (body: { registration_id: number }) =>
      apiRequest<SellerRegistrationResendCodeResponse>('/seller-auth/register/resend-code', {
        method: 'POST',
        body,
      }),
    login: (body: { email: string; password: string }) =>
      apiRequest<TokenResponse>('/seller-auth/login', { method: 'POST', body }),
    me: () => apiRequest<User>('/seller-auth/me'),
  },
  users: {
    me: () => apiRequest<User>('/users/me'),
  },
  categories: {
    list: () => apiRequest<Category[]>('/categories'),
    create: (body: CategoryPayload) =>
      apiRequest<Category>('/categories', { method: 'POST', body }),
    update: (categoryId: number, body: Partial<CategoryPayload>) =>
      apiRequest<Category>(`/categories/${categoryId}`, { method: 'PATCH', body }),
    delete: (categoryId: number) =>
      apiRequest<void>(`/categories/${categoryId}`, { method: 'DELETE' }),
    uploadImage: (file: File, altText?: string) => {
      const formData = new FormData();
      formData.append('file', file);
      if (altText) {
        formData.append('alt_text', altText);
      }
      return apiRequest<UploadedCategoryImage>('/uploads/categories/images', {
        method: 'POST',
        formData,
      });
    },
  },
  tags: {
    list: () => apiRequest<Tag[]>('/tags'),
    create: (body: TagPayload) => apiRequest<Tag>('/tags', { method: 'POST', body }),
    update: (tagId: number, body: Partial<TagPayload>) =>
      apiRequest<Tag>(`/tags/${tagId}`, { method: 'PATCH', body }),
    delete: (tagId: number) => apiRequest<void>(`/tags/${tagId}`, { method: 'DELETE' }),
    uploadImage: (file: File, altText?: string) => {
      const formData = new FormData();
      formData.append('file', file);
      if (altText) {
        formData.append('alt_text', altText);
      }
      return apiRequest<UploadedTagImage>('/uploads/tags/images', {
        method: 'POST',
        formData,
      });
    },
  },
  products: {
    listAdmin: (query: QueryParams = {}) =>
      apiRequest<PageList<Product>>('/products/admin', { query: clampQueryLimit(query, 100) }),
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
    generateVariantSkus: (count: number) =>
      apiRequest<ProductVariantSkuList>('/products/admin/variant-skus/next', {
        query: { count },
      }),
    generateProductSlugs: (count: number) =>
      apiRequest<ProductSlugList>('/products/admin/slugs/next', {
        query: { count },
      }),
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
    sendCustomerMessage: (orderId: number, text: string, photo?: File | null) => {
      const formData = new FormData();
      if (text.trim()) {
        formData.append('text', text.trim());
      }
      if (photo) {
        formData.append('photo', photo);
      }
      return apiRequest<CustomerOrderMessageResponse>(
        `/orders/admin/${orderId}/customer-message`,
        { method: 'POST', formData },
      );
    },
  },
  paymentSettings: {
    get: () => apiRequest<SellerPaymentSettings>('/seller/settings/payment'),
    update: (body: SellerPaymentSettingsPayload) =>
      apiRequest<SellerPaymentSettings>('/seller/settings/payment', {
        method: 'PUT',
        body,
      }),
  },
  manualPayments: {
    list: (status?: ManualPaymentStatus) =>
      apiRequest<PageList<ManualPayment>>('/seller/payments', {
        query: { limit: 100, offset: 0, status },
      }),
    get: (paymentId: number) =>
      apiRequest<ManualPayment>(`/seller/payments/${paymentId}`),
    approve: (paymentId: number) =>
      apiRequest<ManualPayment>(`/seller/payments/${paymentId}/approve`, {
        method: 'POST',
      }),
    reject: (paymentId: number, rejectReason?: string | null) =>
      apiRequest<ManualPayment>(`/seller/payments/${paymentId}/reject`, {
        method: 'POST',
        body: { reject_reason: rejectReason ?? null },
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
    uploadImage: (file: File, altText?: string, imageKind: BannerImageKind = 'native_banner') => {
      const formData = new FormData();
      formData.append('file', file);
      formData.append('image_kind', imageKind);
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
  returns: {
    list: (query: QueryParams = {}) =>
      apiRequest<PageList<ReturnRequest>>('/returns/admin', {
        query: clampQueryLimit(query, 100),
      }),
    get: (returnRequestId: number) =>
      apiRequest<ReturnRequest>(`/returns/admin/${returnRequestId}`),
    approve: (returnRequestId: number, body: ReturnDecisionPayload = {}) =>
      apiRequest<ReturnRequest>(`/returns/admin/${returnRequestId}/approve`, {
        method: 'POST',
        body,
      }),
    reject: (returnRequestId: number, body: ReturnDecisionPayload = {}) =>
      apiRequest<ReturnRequest>(`/returns/admin/${returnRequestId}/reject`, {
        method: 'POST',
        body,
      }),
    complete: (returnRequestId: number, body: ReturnLifecyclePayload = {}) =>
      apiRequest<ReturnRequest>(`/returns/admin/${returnRequestId}/complete`, {
        method: 'POST',
        body,
      }),
    cancel: (returnRequestId: number, body: ReturnLifecyclePayload = {}) =>
      apiRequest<ReturnRequest>(`/returns/admin/${returnRequestId}/cancel`, {
        method: 'POST',
        body,
      }),
    statuses: [
      'PENDING',
      'APPROVED',
      'REJECTED',
      'COMPLETED',
      'CANCELLED',
    ] satisfies ReturnRequestStatus[],
  },
  looks: {
    listAdmin: (query: QueryParams = {}) =>
      apiRequest<PageList<Look>>('/looks/admin', { query: clampQueryLimit(query, 100) }),
    getAdmin: (lookId: number) => apiRequest<Look>(`/looks/admin/${lookId}`),
    create: (body: LookCreatePayload) =>
      apiRequest<Look>('/looks/admin', { method: 'POST', body }),
    update: (lookId: number, body: LookUpdatePayload) =>
      apiRequest<Look>(`/looks/admin/${lookId}`, { method: 'PATCH', body }),
    archive: (lookId: number) =>
      apiRequest<Look>(`/looks/admin/${lookId}`, { method: 'DELETE' }),
    uploadImage: (
      lookId: number,
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
      return apiRequest<UploadedLookImage>(`/looks/admin/${lookId}/images`, {
        method: 'POST',
        formData,
      });
    },
    deleteImage: (lookId: number, imageId: number) =>
      apiRequest<void>(`/looks/admin/${lookId}/images/${imageId}`, { method: 'DELETE' }),
    statuses: ['DRAFT', 'ACTIVE', 'ARCHIVED'] satisfies LookStatus[],
  },
  analytics: {
    summary: (query: QueryParams = {}) =>
      apiRequest<AnalyticsSummary>('/analytics/summary', { query }),
    events: (query: QueryParams = {}) =>
      apiRequest<PageList<AnalyticsEvent>>('/analytics/events', { query }),
  },
  dashboard: {
    summary: () => apiRequest<DashboardSummary>('/admin/dashboard/summary'),
  },
  sellerBot: {
    status: () => apiRequest<SellerBotStatus>('/seller-bot/status'),
    sendTestMessage: (message: string) =>
      apiRequest<SellerBotActionResponse>('/seller-bot/test-message', {
        method: 'POST',
        body: { message },
      }),
    broadcast: (message: string) =>
      apiRequest<SellerBotActionResponse>('/seller-bot/broadcast', {
        method: 'POST',
        body: { message },
      }),
    messages: (query: QueryParams = {}) =>
      apiRequest<PageList<Notification>>('/seller-bot/messages', { query }),
  },
  customerNotifications: {
    subscriptions: (query: QueryParams = {}) =>
      apiRequest<PageList<CustomerNotificationSubscription>>(
        '/customer-notifications/subscriptions',
        { query },
      ),
    templates: (query: QueryParams = {}) =>
      apiRequest<PageList<NotificationTemplate>>('/customer-notifications/templates', { query }),
    createTemplate: (body: NotificationTemplatePayload) =>
      apiRequest<NotificationTemplate>('/customer-notifications/templates', {
        method: 'POST',
        body,
      }),
    updateTemplate: (templateId: number, body: Partial<NotificationTemplatePayload>) =>
      apiRequest<NotificationTemplate>(`/customer-notifications/templates/${templateId}`, {
        method: 'PATCH',
        body,
      }),
    disableTemplate: (templateId: number) =>
      apiRequest<NotificationTemplate>(
        `/customer-notifications/templates/${templateId}/disable`,
        { method: 'POST' },
      ),
    campaigns: (query: QueryParams = {}) =>
      apiRequest<PageList<BroadcastCampaign>>('/customer-notifications/campaigns', { query }),
    createCampaign: (body: BroadcastCampaignPayload) =>
      apiRequest<BroadcastCampaign>('/customer-notifications/campaigns', {
        method: 'POST',
        body,
      }),
    updateCampaign: (campaignId: number, body: Partial<BroadcastCampaignPayload>) =>
      apiRequest<BroadcastCampaign>(`/customer-notifications/campaigns/${campaignId}`, {
        method: 'PATCH',
        body,
      }),
    attachCampaignImage: (campaignId: number, file: File) => {
      const formData = new FormData();
      formData.append('file', file);
      return apiRequest<BroadcastCampaign>(
        `/customer-notifications/campaigns/${campaignId}/image`,
        { method: 'POST', formData },
      );
    },
    removeCampaignImage: (campaignId: number) =>
      apiRequest<BroadcastCampaign>(`/customer-notifications/campaigns/${campaignId}/image`, {
        method: 'DELETE',
      }),
    campaignDetail: (campaignId: number) =>
      apiRequest<BroadcastCampaignDetail>(`/customer-notifications/campaigns/${campaignId}`),
    previewCampaign: (campaignId: number) =>
      apiRequest<BroadcastCampaignPreview>(
        `/customer-notifications/campaigns/${campaignId}/preview`,
        { method: 'POST' },
      ),
    testCampaign: (campaignId: number) =>
      apiRequest<BroadcastCampaignTestResponse>(
        `/customer-notifications/campaigns/${campaignId}/test`,
        { method: 'POST', body: {} },
      ),
    startCampaign: (campaignId: number) =>
      apiRequest<BroadcastCampaign>(`/customer-notifications/campaigns/${campaignId}/start`, {
        method: 'POST',
      }),
    scheduleCampaign: (campaignId: number, scheduledAt?: string | null) =>
      apiRequest<BroadcastCampaign>(`/customer-notifications/campaigns/${campaignId}/schedule`, {
        method: 'POST',
        body: { scheduled_at: scheduledAt ?? null },
      }),
    pauseCampaign: (campaignId: number) =>
      apiRequest<BroadcastCampaign>(`/customer-notifications/campaigns/${campaignId}/pause`, {
        method: 'POST',
      }),
    cancelCampaign: (campaignId: number) =>
      apiRequest<BroadcastCampaign>(`/customer-notifications/campaigns/${campaignId}/cancel`, {
        method: 'POST',
      }),
    processCampaignBatch: (campaignId: number, limit?: number) =>
      apiRequest<BroadcastCampaignProcessBatchResponse>(
        `/customer-notifications/campaigns/${campaignId}/process-batch`,
        { method: 'POST', body: { limit } },
      ),
    deliverySummary: (campaignId: number) =>
      apiRequest<BroadcastDeliverySummary>(
        `/customer-notifications/campaigns/${campaignId}/delivery-summary`,
      ),
    deliveries: (campaignId: number, query: QueryParams = {}) =>
      apiRequest<PageList<BroadcastDelivery>>(
        `/customer-notifications/campaigns/${campaignId}/deliveries`,
        { query },
      ),
  },
  channelEntry: {
    config: () => apiRequest<ChannelEntryConfig>('/channel-entry/config'),
    channels: () => apiRequest<TelegramChannel[]>('/channel-entry/channels'),
    createChannel: (body: TelegramChannelPayload) =>
      apiRequest<TelegramChannel>('/channel-entry/channels', { method: 'POST', body }),
    updateChannel: (channelId: number, body: Partial<TelegramChannelPayload & { is_active: boolean }>) =>
      apiRequest<TelegramChannel>(`/channel-entry/channels/${channelId}`, {
        method: 'PATCH',
        body,
      }),
    disableChannel: (channelId: number) =>
      apiRequest<void>(`/channel-entry/channels/${channelId}`, { method: 'DELETE' }),
    checkChannel: (chatId: string) =>
      apiRequest<TelegramChannelCheckResponse>('/channel-entry/channels/check', {
        method: 'POST',
        body: { chat_id: chatId },
      }),
    preview: (body: ChannelEntryPreviewPayload) =>
      apiRequest<ChannelEntryPreview>('/channel-entry/preview', { method: 'POST', body }),
    publish: (body: ChannelEntryPublishPayload) =>
      apiRequest<ChannelEntryPublishResponse>('/channel-entry/publish', {
        method: 'POST',
        body,
      }),
    history: (query: QueryParams = {}) =>
      apiRequest<PageList<TelegramChannelEntryMessage>>('/channel-entry/history', { query }),
    pinMessage: (messageId: number) =>
      apiRequest<TelegramChannelEntryMessage>(`/channel-entry/messages/${messageId}/pin`, {
        method: 'POST',
      }),
  },
};
