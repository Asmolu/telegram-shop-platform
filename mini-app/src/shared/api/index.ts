import { apiRequest, type ApiRequestOptions } from './client';
import type {
  BannerList,
  Cart,
  Category,
  CheckoutPayload,
  CustomerNotificationStartLink,
  CustomerNotificationSubscription,
  CustomerNotificationSubscriptionUpdate,
  CustomerNotificationWriteAccessRequest,
  Favorite,
  FavoriteList,
  ManualPayment,
  Order,
  OrderList,
  PersonalData,
  PersonalDataUpdate,
  Product,
  ProductList,
  ProductSearchSuggestionList,
  ProductSizeGrid,
  PromoValidation,
  Review,
  ReviewList,
  Tag,
  TokenResponse,
  User,
} from './types';

export * from './client';
export type * from './types';

export type ProductListParams = {
  limit?: number;
  offset?: number;
  category_id?: number;
  tag_id?: number;
  status?: string;
  search?: string;
  size_grid?: ProductSizeGrid;
  size?: string;
  color?: string;
};

export function loginWithTelegram(initData: string) {
  return apiRequest<TokenResponse>('/auth/telegram/login', {
    method: 'POST',
    body: JSON.stringify({ init_data: initData }),
  });
}

export function getCurrentUser(options: ApiRequestOptions = {}) {
  return apiRequest<User>('/users/me', options);
}

export function getPersonalData(options: ApiRequestOptions = {}) {
  return apiRequest<PersonalData>('/users/me/personal-data', options);
}

export function updatePersonalData(payload: PersonalDataUpdate) {
  return apiRequest<PersonalData>('/users/me/personal-data', {
    method: 'PUT',
    body: JSON.stringify(payload),
  });
}

export function getProducts(params: ProductListParams = {}, options: ApiRequestOptions = {}) {
  return apiRequest<ProductList>('/products', { ...options, query: params });
}

export function getProductSearchSuggestions(
  query: string,
  limit = 8,
  options: ApiRequestOptions = {},
) {
  return apiRequest<ProductSearchSuggestionList>('/products/suggestions', {
    ...options,
    query: { query, limit },
  });
}

export function getProduct(productId: number, options: ApiRequestOptions = {}) {
  return apiRequest<Product>(`/products/${productId}`, options);
}

export function getCategories(options: ApiRequestOptions = {}) {
  return apiRequest<Category[]>('/categories', options);
}

export function getCategory(categoryId: number, options: ApiRequestOptions = {}) {
  return apiRequest<Category>(`/categories/${categoryId}`, options);
}

export function getTags(options: ApiRequestOptions = {}) {
  return apiRequest<Tag[]>('/tags', options);
}

export function getBanners(options: ApiRequestOptions = {}) {
  return apiRequest<BannerList>('/banners', { ...options, query: { limit: 20, offset: 0 } });
}

export function trackBannerClick(bannerId: number) {
  return apiRequest(`/banners/${bannerId}/click`, { method: 'POST', networkImpact: 'local' });
}

export function getCart(options: ApiRequestOptions = {}) {
  return apiRequest<Cart>('/cart', options);
}

export function addCartItem(
  productId: number,
  productVariantId: number,
  quantity = 1,
  options: ApiRequestOptions = {},
) {
  return apiRequest<Cart>('/cart/items', {
    ...options,
    method: 'POST',
    networkImpact: options.networkImpact ?? 'local',
    body: JSON.stringify({
      product_id: productId,
      product_variant_id: productVariantId,
      quantity,
    }),
  });
}

export function updateCartItem(itemId: number, quantity: number) {
  return apiRequest<Cart>(`/cart/items/${itemId}`, {
    method: 'PATCH',
    networkImpact: 'local',
    body: JSON.stringify({ quantity }),
  });
}

export function updateCartItemSelection(itemId: number, isSelected: boolean) {
  return apiRequest<Cart>(`/cart/items/${itemId}/selection`, {
    method: 'PATCH',
    networkImpact: 'local',
    body: JSON.stringify({ is_selected: isSelected }),
  });
}

export function updateCartSelection(isSelected: boolean, itemIds?: number[]) {
  return apiRequest<Cart>('/cart/selection', {
    method: 'PATCH',
    networkImpact: 'local',
    body: JSON.stringify({
      is_selected: isSelected,
      item_ids: itemIds,
    }),
  });
}

export function removeCartItem(itemId: number) {
  return apiRequest<Cart>(`/cart/items/${itemId}`, { method: 'DELETE', networkImpact: 'local' });
}

export function getFavorites(options: ApiRequestOptions = {}) {
  return apiRequest<FavoriteList>('/favorites', options);
}

export function addFavorite(productId: number, options: ApiRequestOptions = {}) {
  return apiRequest<Favorite>('/favorites', {
    ...options,
    method: 'POST',
    networkImpact: options.networkImpact ?? 'local',
    body: JSON.stringify({ product_id: productId }),
  });
}

export function removeFavorite(productId: number, options: ApiRequestOptions = {}) {
  return apiRequest<void>(`/favorites/${productId}`, {
    ...options,
    method: 'DELETE',
    networkImpact: options.networkImpact ?? 'local',
  });
}

export function validatePromoCode(code: string) {
  return apiRequest<PromoValidation>('/promo-codes/validate', {
    method: 'POST',
    body: JSON.stringify({ code }),
  });
}

export function checkoutCart(payload: CheckoutPayload, idempotencyKey?: string) {
  return apiRequest<Order>('/orders/checkout', {
    method: 'POST',
    idempotencyKey,
    body: JSON.stringify(payload),
  });
}

export function getOrders(options: ApiRequestOptions = {}) {
  return apiRequest<OrderList>('/orders', { ...options, query: { limit: 50, offset: 0 } });
}

export function getOrder(orderId: number, options: ApiRequestOptions = {}) {
  return apiRequest<Order>(`/orders/${orderId}`, options);
}

export function getOrderPayment(orderId: number, options: ApiRequestOptions = {}) {
  return apiRequest<ManualPayment>(`/orders/${orderId}/payment`, options);
}

export function submitOrderPayment(orderId: number, idempotencyKey?: string) {
  return apiRequest<ManualPayment>(`/orders/${orderId}/payment/submit`, {
    method: 'POST',
    idempotencyKey,
  });
}

export function uploadOrderPaymentReceipt(orderId: number, file: File, idempotencyKey?: string) {
  const body = new FormData();
  body.append('file', file);
  return apiRequest<ManualPayment>(`/orders/${orderId}/payment/receipt`, {
    method: 'POST',
    idempotencyKey,
    body,
  });
}

export function getProductReviews(productId: number) {
  return apiRequest<ReviewList>(`/products/${productId}/reviews`);
}

export function createProductReview(productId: number, rating: number, text: string) {
  return apiRequest<Review>(`/products/${productId}/reviews`, {
    method: 'POST',
    body: JSON.stringify({ rating, text }),
  });
}

export function getCustomerNotificationSubscription(options: ApiRequestOptions = {}) {
  return apiRequest<CustomerNotificationSubscription>(
    '/customer-notifications/me/subscription',
    options,
  );
}

export function updateCustomerNotificationSubscription(
  payload: CustomerNotificationSubscriptionUpdate,
) {
  return apiRequest<CustomerNotificationSubscription>('/customer-notifications/me/subscription', {
    method: 'PATCH',
    body: JSON.stringify(payload),
  });
}

export function recordCustomerNotificationWriteAccess(
  payload: CustomerNotificationWriteAccessRequest,
) {
  return apiRequest<CustomerNotificationSubscription>('/customer-notifications/me/write-access', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function createCustomerNotificationStartLink() {
  return apiRequest<CustomerNotificationStartLink>('/customer-notifications/me/start-link', {
    method: 'POST',
  });
}
