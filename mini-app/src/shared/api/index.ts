import { apiRequest } from './client';
import type {
  BannerList,
  Cart,
  Category,
  CheckoutPayload,
  CustomerNotificationStartLink,
  CustomerNotificationSubscription,
  CustomerNotificationSubscriptionUpdate,
  Favorite,
  FavoriteList,
  Order,
  OrderList,
  PersonalData,
  PersonalDataUpdate,
  Product,
  ProductList,
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

export function getCurrentUser() {
  return apiRequest<User>('/users/me');
}

export function getPersonalData() {
  return apiRequest<PersonalData>('/users/me/personal-data');
}

export function updatePersonalData(payload: PersonalDataUpdate) {
  return apiRequest<PersonalData>('/users/me/personal-data', {
    method: 'PUT',
    body: JSON.stringify(payload),
  });
}

export function getProducts(params: ProductListParams = {}) {
  return apiRequest<ProductList>('/products', { query: params });
}

export function getProduct(productId: number) {
  return apiRequest<Product>(`/products/${productId}`);
}

export function getCategories() {
  return apiRequest<Category[]>('/categories');
}

export function getCategory(categoryId: number) {
  return apiRequest<Category>(`/categories/${categoryId}`);
}

export function getTags() {
  return apiRequest<Tag[]>('/tags');
}

export function getBanners() {
  return apiRequest<BannerList>('/banners', { query: { limit: 20, offset: 0 } });
}

export function trackBannerClick(bannerId: number) {
  return apiRequest(`/banners/${bannerId}/click`, { method: 'POST' });
}

export function getCart() {
  return apiRequest<Cart>('/cart');
}

export function addCartItem(productId: number, productVariantId: number, quantity = 1) {
  return apiRequest<Cart>('/cart/items', {
    method: 'POST',
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
    body: JSON.stringify({ quantity }),
  });
}

export function removeCartItem(itemId: number) {
  return apiRequest<Cart>(`/cart/items/${itemId}`, { method: 'DELETE' });
}

export function getFavorites() {
  return apiRequest<FavoriteList>('/favorites');
}

export function addFavorite(productId: number) {
  return apiRequest<Favorite>('/favorites', {
    method: 'POST',
    body: JSON.stringify({ product_id: productId }),
  });
}

export function removeFavorite(productId: number) {
  return apiRequest<void>(`/favorites/${productId}`, { method: 'DELETE' });
}

export function validatePromoCode(code: string) {
  return apiRequest<PromoValidation>('/promo-codes/validate', {
    method: 'POST',
    body: JSON.stringify({ code }),
  });
}

export function checkoutCart(payload: CheckoutPayload) {
  return apiRequest<Order>('/orders/checkout', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function getOrders() {
  return apiRequest<OrderList>('/orders', { query: { limit: 50, offset: 0 } });
}

export function getOrder(orderId: number) {
  return apiRequest<Order>(`/orders/${orderId}`);
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

export function getCustomerNotificationSubscription() {
  return apiRequest<CustomerNotificationSubscription>('/customer-notifications/me/subscription');
}

export function updateCustomerNotificationSubscription(
  payload: CustomerNotificationSubscriptionUpdate,
) {
  return apiRequest<CustomerNotificationSubscription>('/customer-notifications/me/subscription', {
    method: 'PATCH',
    body: JSON.stringify(payload),
  });
}

export function createCustomerNotificationStartLink() {
  return apiRequest<CustomerNotificationStartLink>('/customer-notifications/me/start-link', {
    method: 'POST',
  });
}
