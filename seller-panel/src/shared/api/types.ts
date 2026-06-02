export type UserRole = 'USER' | 'SELLER' | 'ADMIN';
export type ProductStatus = 'DRAFT' | 'ACTIVE' | 'OUT_OF_STOCK' | 'ARCHIVED';
export type OrderStatus = 'NEW' | 'PROCESSING' | 'SHIPPED' | 'DELIVERED' | 'CANCELLED';
export type ReviewStatus = 'PENDING' | 'APPROVED' | 'REJECTED';
export type DiscountType = 'PERCENT' | 'FIXED';
export type BannerTargetType = 'product' | 'category' | 'promo' | 'external_url';

export type ApiDecimal = string | number;

export interface PageMeta {
  limit: number;
  offset: number;
  total: number | null;
}

export interface PageList<T> {
  items: T[];
  meta?: PageMeta;
}

export interface User {
  id: number;
  telegram_id: number;
  username: string | null;
  first_name: string | null;
  last_name: string | null;
  phone: string | null;
  role: UserRole;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  user: User;
}

export interface SellerRegistrationStartResponse {
  registration_id: number;
  bot_start_link: string | null;
  start_command: string;
  expires_at: string;
}

export interface SellerTelegramStartResponse {
  registration_id: number;
  telegram_username: string | null;
  status: 'PENDING' | 'AWAITING_APPROVAL' | 'APPROVED' | 'VERIFIED' | 'EXPIRED' | 'REJECTED';
  approval_expires_at: string | null;
  verification_expires_at: string | null;
}

export interface SellerRegistrationResendCodeResponse {
  registration_id: number;
  verification_expires_at: string;
}

export interface Category {
  id: number;
  name: string;
  slug: string;
  description: string | null;
  created_at: string;
  updated_at: string;
}

export interface Tag {
  id: number;
  name: string;
  slug: string;
  created_at: string;
  updated_at: string;
}

export interface ProductImage {
  id: number;
  product_id: number;
  file_path: string;
  url: string;
  alt_text: string | null;
  position: number;
  is_primary: boolean;
  original_filename: string | null;
  mime_type: string | null;
  size_bytes: number | null;
  created_at: string;
}

export interface ProductVariant {
  id: number;
  product_id: number;
  size: string;
  color: string | null;
  sku: string;
  stock_quantity: number;
  reserved_quantity: number;
  available_quantity: number;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface Product {
  id: number;
  name: string;
  slug: string;
  description: string | null;
  base_price: ApiDecimal;
  status: ProductStatus;
  category_id: number | null;
  category: Category | null;
  tags: Tag[];
  images: ProductImage[];
  variants: ProductVariant[];
  is_available: boolean;
  created_at: string;
  updated_at: string;
}

export interface ProductImageCreate {
  file_path: string;
  alt_text?: string | null;
  position?: number;
  is_primary?: boolean;
}

export interface ProductCreate {
  name: string;
  slug: string;
  description?: string | null;
  base_price: string;
  status: ProductStatus;
  category_id?: number | null;
  tag_ids: number[];
  images: ProductImageCreate[];
}

export interface ProductUpdate {
  name?: string;
  slug?: string;
  description?: string | null;
  base_price?: string;
  status?: ProductStatus;
  category_id?: number | null;
  tag_ids?: number[];
  images?: ProductImageCreate[];
}

export interface ProductVariantPayload {
  size: string;
  color?: string | null;
  sku: string;
  stock_quantity: number;
  reserved_quantity: number;
  is_active: boolean;
}

export interface UploadedProductImage extends ProductImage {}

export interface UploadedBannerImage {
  id: number;
  file_path: string;
  url: string;
  original_filename: string;
  mime_type: string;
  size_bytes: number;
  alt_text: string | null;
  created_at: string;
}

export interface OrderItem {
  id: number;
  product_id: number;
  product_variant_id: number;
  product_name: string;
  variant_size: string;
  variant_sku: string;
  unit_price: ApiDecimal;
  quantity: number;
  subtotal: ApiDecimal;
  created_at: string;
}

export interface Order {
  id: number;
  order_number: string;
  user_id: number;
  status: OrderStatus;
  subtotal_amount: ApiDecimal;
  discount_amount: ApiDecimal;
  promo_code_id: number | null;
  promo_code_code: string | null;
  total_amount: ApiDecimal;
  contact_name: string;
  contact_phone: string;
  delivery_address: string;
  delivery_comment: string | null;
  items: OrderItem[];
  created_at: string;
  updated_at: string;
}

export interface Banner {
  id: number;
  title: string;
  subtitle: string | null;
  image_path: string;
  image_url: string;
  target_type: BannerTargetType | null;
  target_id: number | null;
  external_url: string | null;
  position: number;
  is_active: boolean;
  starts_at: string | null;
  ends_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface BannerPayload {
  title: string;
  subtitle?: string | null;
  image_path: string;
  target_type: BannerTargetType;
  target_id?: number | null;
  external_url?: string | null;
  position: number;
  is_active: boolean;
  starts_at?: string | null;
  ends_at?: string | null;
}

export interface PromoCode {
  id: number;
  code: string;
  discount_type: DiscountType;
  discount_value: ApiDecimal;
  is_active: boolean;
  starts_at: string | null;
  ends_at: string | null;
  usage_limit: number | null;
  per_user_limit: number | null;
  created_at: string;
  updated_at: string;
}

export interface PromoCodePayload {
  code: string;
  discount_type: DiscountType;
  discount_value: string;
  is_active: boolean;
  starts_at?: string | null;
  ends_at?: string | null;
  usage_limit?: number | null;
  per_user_limit?: number | null;
}

export interface Review {
  id: number;
  user_id: number;
  product_id: number;
  order_id: number | null;
  rating: number;
  text: string;
  status: ReviewStatus;
  moderated_at: string | null;
  moderated_by_id: number | null;
  created_at: string;
  updated_at: string;
}

export interface AnalyticsSummary {
  total_orders: number;
  total_revenue: ApiDecimal;
  product_views_count: number;
  cart_item_added_count: number;
  checkout_started_count: number;
  promo_used_count: number;
  top_products: Array<{
    product_id: number;
    product_name: string | null;
    view_count: number;
  }>;
}

export interface AnalyticsEvent {
  id: number;
  event_name: string;
  user_id: number | null;
  product_id: number | null;
  order_id: number | null;
  promo_code_id: number | null;
  banner_id: number | null;
  metadata: Record<string, unknown> | null;
  created_at: string;
}

export type NotificationChannel = 'telegram' | 'internal';
export type NotificationStatus = 'pending' | 'sent' | 'failed';

export interface Notification {
  id: number;
  user_id: number | null;
  type: string;
  title: string;
  message: string;
  payload: Record<string, unknown> | null;
  channel: NotificationChannel;
  status: NotificationStatus;
  error_message: string | null;
  sent_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface SellerBotStatus {
  configured: boolean;
  seller_chat_configured: boolean;
  ok: boolean;
  bot: Record<string, unknown> | null;
  error: string | null;
}

export interface SellerBotActionResponse {
  notification_id: number;
  status: NotificationStatus;
  message: string;
}
