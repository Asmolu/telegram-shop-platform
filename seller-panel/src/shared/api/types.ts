export type UserRole = 'USER' | 'SELLER' | 'ADMIN';
export type ProductStatus = 'DRAFT' | 'ACTIVE' | 'OUT_OF_STOCK' | 'ARCHIVED';
export type ProductSizeGrid = 'clothing_alpha' | 'shoes_eu' | 'shoes_ru';
export type ProductSizeGroup = 'CLOTHING' | 'FOOTWEAR' | 'ONE_SIZE';
export type ProductImageBadgeType = 'none' | 'new' | 'sale' | 'hit' | 'exclusive' | 'custom';
export type ProductImageBadgeColor =
  | 'purple'
  | 'pink'
  | 'red'
  | 'orange'
  | 'blue'
  | 'green'
  | 'black'
  | 'white';
export type ProductImageBadgePosition = 'top-left' | 'top-right' | 'bottom-left' | 'bottom-right';
export type OrderStatus = 'NEW' | 'PROCESSING' | 'SHIPPED' | 'DELIVERED' | 'CANCELLED';
export type OrderDeliveryMethod =
  | 'ROUTE_TAXI'
  | 'CITY_DELIVERY'
  | 'OZON'
  | 'WB'
  | 'CDEK'
  | 'PICKUP';
export type ItemSourceType = 'LOOK' | string;
export type ManualPaymentStatus =
  | 'PENDING'
  | 'SUBMITTED'
  | 'APPROVED'
  | 'REJECTED'
  | 'EXPIRED'
  | 'CANCELLED';
export type ReviewStatus = 'PENDING' | 'APPROVED' | 'REJECTED';
export type ReturnRequestStatus =
  | 'PENDING'
  | 'APPROVED'
  | 'REJECTED'
  | 'COMPLETED'
  | 'CANCELLED';
export type ReturnRefundStatus = 'PENDING' | 'RECORDED';
export type LookStatus = 'DRAFT' | 'ACTIVE' | 'ARCHIVED';
export type DiscountType = 'PERCENT' | 'FIXED';
export type BannerTargetType = 'product' | 'category' | 'promo' | 'external_url';
export type BannerDisplayType = 'horizontal' | 'vertical' | 'popup' | 'aggressive_popup';
export type BannerImageKind = 'native_banner' | 'vertical_banner' | 'popup_banner' | 'aggressive_banner';
export type ChannelEntryButtonStyle = 'default' | 'primary' | 'secondary' | 'danger' | 'success';

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

export interface UserBlockUser {
  id: number;
  telegram_id: number;
  username: string | null;
  telegram_username: string | null;
}

export interface UserBlock {
  id: number;
  user_id: number | null;
  telegram_id: number | null;
  telegram_username: string | null;
  reason: string | null;
  blocked_at: string;
  blocked_by_user_id: number | null;
  unblocked_at: string | null;
  unblocked_by_user_id: number | null;
  user: UserBlockUser | null;
  blocked_by: UserBlockUser | null;
}

export interface UserBlockPayload {
  telegram_id?: number | null;
  telegram_username?: string | null;
  reason?: string | null;
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
  image_path: string | null;
  image_url: string | null;
  created_at: string;
  updated_at: string;
}

export interface CategoryPayload {
  name: string;
  slug: string;
  description?: string | null;
  image_path?: string | null;
}

export interface Tag {
  id: number;
  name: string;
  slug: string;
  image_path: string | null;
  image_url: string | null;
  created_at: string;
  updated_at: string;
}

export interface TagPayload {
  name: string;
  slug: string;
  image_path?: string | null;
}

export interface ProductImage {
  id: number;
  product_id: number;
  file_path: string;
  url: string;
  image_url?: string | null;
  thumbnail_path?: string | null;
  card_path?: string | null;
  detail_path?: string | null;
  thumbnail_url?: string | null;
  card_url?: string | null;
  detail_url?: string | null;
  image_variants?: {
    thumbnail?: string | null;
    card?: string | null;
    detail?: string | null;
  } | null;
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

export interface ProductVariantSkuList {
  items: string[];
}

export interface ProductCategoryAssignment {
  category_id: number;
  priority: 1 | 2 | 3;
  category?: Category | null;
}

export interface Product {
  id: number;
  name: string;
  slug: string;
  brand: string | null;
  description: string | null;
  base_price: ApiDecimal;
  old_price: ApiDecimal | null;
  search_priority: 1 | 2 | 3;
  search_aliases: string | null;
  size_grid: ProductSizeGrid;
  size_group: ProductSizeGroup;
  image_badge_type: ProductImageBadgeType;
  image_badge_text: string | null;
  image_badge_color: ProductImageBadgeColor | null;
  image_badge_position: ProductImageBadgePosition | null;
  status: ProductStatus;
  is_listed: boolean;
  is_returnable: boolean;
  category_id: number | null;
  category: Category | null;
  categories: ProductCategoryAssignment[];
  tags: Tag[];
  images: ProductImage[];
  variants: ProductVariant[];
  related_product_ids?: number[];
  related_products?: Product[];
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
  slug?: string | null;
  brand?: string | null;
  description?: string | null;
  base_price: string;
  old_price?: string | null;
  search_priority?: 1 | 2 | 3;
  search_aliases?: string | null;
  size_grid?: ProductSizeGrid;
  size_group?: ProductSizeGroup;
  image_badge_type?: ProductImageBadgeType;
  image_badge_text?: string | null;
  image_badge_color?: ProductImageBadgeColor | null;
  image_badge_position?: ProductImageBadgePosition | null;
  status: ProductStatus;
  is_listed?: boolean;
  is_returnable?: boolean;
  category_id?: number | null;
  categories?: ProductCategoryAssignment[];
  tag_ids: number[];
  images: ProductImageCreate[];
  related_product_ids?: number[];
}

export interface ProductUpdate {
  name?: string;
  slug?: string;
  brand?: string | null;
  description?: string | null;
  base_price?: string;
  old_price?: string | null;
  search_priority?: 1 | 2 | 3;
  search_aliases?: string | null;
  size_grid?: ProductSizeGrid;
  size_group?: ProductSizeGroup;
  image_badge_type?: ProductImageBadgeType;
  image_badge_text?: string | null;
  image_badge_color?: ProductImageBadgeColor | null;
  image_badge_position?: ProductImageBadgePosition | null;
  status?: ProductStatus;
  is_listed?: boolean;
  is_returnable?: boolean;
  category_id?: number | null;
  categories?: ProductCategoryAssignment[];
  tag_ids?: number[];
  images?: ProductImageCreate[];
  related_product_ids?: number[];
}

export interface ProductVariantPayload {
  size: string;
  color?: string | null;
  sku: string;
  stock_quantity: number;
  reserved_quantity: number;
  is_active: boolean;
}

export interface ProductSlugList {
  items: string[];
}

export interface UploadedProductImage extends ProductImage {}

export interface UploadedBannerImage {
  file_path: string;
  url: string;
  original_filename: string;
  mime_type: string;
  size_bytes: number;
  alt_text: string | null;
}

export interface UploadedTagImage extends UploadedBannerImage {}

export interface UploadedCategoryImage extends UploadedBannerImage {}

export interface UploadedChannelEntryPhoto extends UploadedBannerImage {}

export interface OrderItem {
  id: number;
  product_id: number;
  product_variant_id: number;
  product_name: string;
  product_title?: string;
  variant_size: string;
  variant_size_grid: ProductSizeGrid;
  variant_color?: string | null;
  variant_sku: string;
  unit_price: ApiDecimal;
  quantity: number;
  subtotal: ApiDecimal;
  is_returnable: boolean;
  item_total?: ApiDecimal;
  product_thumbnail_path?: string | null;
  product_thumbnail_url?: string | null;
  source_type?: ItemSourceType | null;
  source_group_id?: string | null;
  source_look_id?: number | null;
  source_look_slug?: string | null;
  source_look_title?: string | null;
  source_look_image_url?: string | null;
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
  delivery_price?: ApiDecimal;
  contact_name: string;
  contact_phone: string;
  delivery_method: OrderDeliveryMethod | null;
  delivery_address: string;
  delivery_comment: string | null;
  manual_payment?: {
    id: number;
    status: ManualPaymentStatus;
    expires_at: string;
    submitted_at: string | null;
    receipt_image_path: string | null;
    receipt_image_url: string | null;
  } | null;
  items: OrderItem[];
  delivered_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface CustomerOrderMessageResponse {
  ok: boolean;
  order_id: number;
  delivery_id: number;
  telegram_message_id: number | null;
  sent_text: boolean;
  sent_photo: boolean;
}

export interface ReturnRequestItem {
  id: number;
  order_item_id: number;
  product_id: number | null;
  product_variant_id: number | null;
  product_name: string;
  product_brand: string | null;
  sku: string | null;
  size: string | null;
  color: string | null;
  unit_price: ApiDecimal;
  quantity: number;
  restocked_quantity: number;
  restocked_at: string | null;
  restocked_by_user_id: number | null;
  remaining_restockable_quantity: number;
  can_restock: boolean;
  created_at: string;
}

export interface ReturnRequestAttachment {
  id: number;
  file_path: string;
  original_filename: string;
  mime_type: string;
  size_bytes: number;
  media_type: 'image' | 'video';
  position: number;
  url: string;
  created_at: string;
}

export interface ReturnRefund {
  id: number;
  return_request_id: number;
  amount: ApiDecimal;
  currency: string;
  method: string | null;
  status: ReturnRefundStatus;
  comment: string | null;
  processed_at: string | null;
  processed_by_user_id: number | null;
  created_at: string;
  updated_at: string;
}

export interface ReturnRequest {
  id: number;
  return_number: string;
  order_id: number;
  order_number: string | null;
  order_status: OrderStatus | null;
  user_id: number;
  customer_name: string | null;
  customer_phone: string | null;
  status: ReturnRequestStatus;
  reason: string;
  comment: string | null;
  items: ReturnRequestItem[];
  attachments: ReturnRequestAttachment[];
  refund: ReturnRefund | null;
  total_return_amount: ApiDecimal;
  can_process: boolean;
  can_complete: boolean;
  decided_at: string | null;
  decided_by_user_id: number | null;
  decision_comment: string | null;
  completed_at: string | null;
  completed_by_user_id: number | null;
  completion_comment: string | null;
  cancelled_at: string | null;
  cancelled_by_user_id: number | null;
  cancellation_comment: string | null;
  message: string | null;
  created_at: string;
  updated_at: string;
}

export interface ReturnDecisionPayload {
  decision_comment?: string | null;
}

export interface ReturnLifecyclePayload {
  comment?: string | null;
}

export interface ReturnProcessPayload {
  refund?: {
    amount?: ApiDecimal | null;
    currency?: string;
    method?: string | null;
    comment?: string | null;
  } | null;
  restock_items?: Array<{
    return_request_item_id: number;
    quantity: number;
  }>;
  complete?: boolean;
  comment?: string | null;
}

export interface LookImage {
  id: number;
  look_id: number;
  file_path: string;
  url: string;
  image_url?: string | null;
  original_filename: string | null;
  mime_type: string | null;
  size_bytes: number | null;
  alt_text: string | null;
  position: number;
  is_primary: boolean;
  created_at: string;
}

export interface LookItem {
  id: number;
  look_id: number;
  product_id: number;
  position: number;
  quantity: number;
  is_default_selected: boolean;
  created_at: string;
  updated_at: string;
}

export interface Look {
  id: number;
  slug: string;
  title: string;
  description: string | null;
  status: LookStatus;
  is_listed: boolean;
  search_priority: 1 | 2 | 3;
  images: LookImage[];
  items: LookItem[];
  created_at: string;
  updated_at: string;
}

export interface LookSlugList {
  items: string[];
}

export interface LookItemPayload {
  product_id: number;
  position?: number;
  quantity?: number;
  is_default_selected?: boolean;
}

export interface LookCreatePayload {
  title: string;
  slug: string;
  description?: string | null;
  status?: LookStatus;
  is_listed?: boolean;
  search_priority?: 1 | 2 | 3;
  items?: LookItemPayload[];
}

export interface LookUpdatePayload {
  title?: string;
  slug?: string;
  description?: string | null;
  status?: LookStatus;
  is_listed?: boolean;
  search_priority?: 1 | 2 | 3;
  items?: LookItemPayload[];
}

export interface UploadedLookImage extends LookImage {}

export interface SellerPaymentSettings {
  is_manual_sbp_enabled: boolean;
  seller_phone_e164: string | null;
  seller_phone_display: string | null;
  seller_bank_name: string | null;
  seller_recipient_name: string | null;
  updated_at: string | null;
}

export interface SellerPaymentSettingsPayload {
  is_manual_sbp_enabled: boolean;
  seller_phone: string | null;
  seller_bank_name: string | null;
  seller_recipient_name: string | null;
}

export interface PaymentSuccessBannerSettings {
  enabled: boolean;
  image_path: string | null;
  image_url: string | null;
  updated_at: string | null;
}

export interface PaymentSuccessBannerSettingsPayload {
  enabled: boolean;
  image_path: string | null;
}

export interface SellerContactSettings {
  telegram_url: string | null;
  whatsapp_url: string | null;
  instagram_url: string | null;
  updated_at: string | null;
}

export interface SellerContactSettingsPayload {
  telegram_url: string | null;
  whatsapp_url: string | null;
  instagram_url: string | null;
}

export interface ManualPayment {
  id: number;
  order_id: number;
  order_number: string;
  order_status: OrderStatus;
  customer_user_id: number;
  customer_name: string;
  customer_phone: string;
  delivery_method: OrderDeliveryMethod | null;
  delivery_price?: ApiDecimal;
  method: 'SBP_PHONE';
  amount: ApiDecimal;
  currency: 'RUB';
  status: ManualPaymentStatus;
  expires_at: string;
  server_now: string;
  seller_phone_display: string;
  seller_phone_e164: string;
  seller_bank_name: string | null;
  seller_recipient_name: string | null;
  payment_comment: string;
  receipt_image_path: string | null;
  receipt_image_url: string | null;
  submitted_at: string | null;
  approved_at: string | null;
  rejected_at: string | null;
  reject_reason: string | null;
  stock_released_at: string | null;
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
  display_type: BannerDisplayType;
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
  display_type?: BannerDisplayType;
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
  order_created_count?: number;
  promo_used_count: number;
  banner_clicked_count?: number;
  top_products: Array<{
    product_id: number;
    product_name: string | null;
    view_count: number;
  }>;
  top_promo_codes?: Array<{
    promo_code_id: number;
    promo_code: string | null;
    used_count: number;
  }>;
  top_banners?: Array<{
    banner_id: number;
    banner_title: string | null;
    click_count: number;
  }>;
}

export interface DashboardRevenueMonth {
  period_start: string;
  period_end: string;
  orders_count: number;
  gross_revenue: ApiDecimal;
  discount_total: ApiDecimal;
  net_revenue: ApiDecimal;
}

export interface DashboardSummary {
  active_orders_count: number;
  active_banners_count: number;
  products_total: number;
  products_out_of_stock: number;
  revenue_month: DashboardRevenueMonth;
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

export interface CustomerNotificationSubscription {
  id: number;
  user_id: number | null;
  telegram_user_id: number;
  telegram_chat_id_masked: string | null;
  telegram_username: string | null;
  telegram_first_name: string | null;
  telegram_last_name: string | null;
  chat_type: string;
  has_chat: boolean;
  service_opt_in: boolean;
  marketing_opt_in: boolean;
  blocked_at: string | null;
  last_start_at: string | null;
  last_stop_at: string | null;
  last_settings_at: string | null;
  last_delivery_error: string | null;
  created_at: string;
  updated_at: string;
}

export type NotificationTemplateCategory = 'service' | 'marketing';
export type BroadcastCampaignType = 'service' | 'marketing';
export type BroadcastCampaignStatus =
  | 'draft'
  | 'scheduled'
  | 'sending'
  | 'paused'
  | 'completed'
  | 'cancelled'
  | 'failed';
export type BroadcastDeliveryStatus =
  | 'pending'
  | 'sending'
  | 'sent'
  | 'failed'
  | 'skipped'
  | 'blocked'
  | 'rate_limited';

export interface NotificationTemplate {
  id: number;
  key: string;
  name: string;
  category: NotificationTemplateCategory;
  channel: NotificationChannel;
  title: string | null;
  body_template: string;
  parse_mode: string | null;
  allowed_variables: string[];
  is_active: boolean;
  created_by_user_id: number | null;
  updated_by_user_id: number | null;
  created_at: string;
  updated_at: string;
}

export interface NotificationTemplatePayload {
  key: string;
  name: string;
  category: NotificationTemplateCategory;
  channel?: NotificationChannel;
  title?: string | null;
  body_template: string;
  parse_mode?: string | null;
  allowed_variables: string[];
  is_active?: boolean;
}

export interface BroadcastCampaign {
  id: number;
  template_id: number | null;
  name: string;
  type: BroadcastCampaignType;
  status: BroadcastCampaignStatus;
  audience_filter: Record<string, unknown>;
  recipient_count_estimate: number;
  recipient_count_final: number | null;
  message_title: string | null;
  message_body: string;
  parse_mode: string | null;
  image_path: string | null;
  image_url: string | null;
  image_original_filename: string | null;
  image_mime_type: string | null;
  image_size_bytes: number | null;
  scheduled_at: string | null;
  started_at: string | null;
  completed_at: string | null;
  created_by_user_id: number;
  approved_by_user_id: number | null;
  cancelled_by_user_id: number | null;
  created_at: string;
  updated_at: string;
}

export interface BroadcastCampaignPayload {
  template_id?: number | null;
  name: string;
  type: BroadcastCampaignType;
  audience_filter: Record<string, unknown>;
  message_title?: string | null;
  message_body?: string | null;
  parse_mode?: string | null;
  scheduled_at?: string | null;
  template_variables?: Record<string, unknown>;
}

export interface BroadcastDeliverySummary {
  pending: number;
  sending: number;
  sent: number;
  failed: number;
  skipped: number;
  blocked: number;
  rate_limited: number;
  total: number;
}

export interface BroadcastCampaignDetail {
  campaign: BroadcastCampaign;
  delivery_summary: BroadcastDeliverySummary;
}

export interface BroadcastCampaignPreview {
  campaign_id: number;
  recipient_count_estimate: number;
  rendered_sample: string;
  eligibility_warnings: string[];
}

export interface BroadcastCampaignTestResponse {
  ok: boolean;
  campaign_id: number;
  telegram_message_id: number | null;
  recipient_user_id: number | null;
  recipient_username: string | null;
}

export interface BroadcastCampaignProcessBatchResponse {
  campaign_id: number;
  processed: number;
  sent: number;
  failed: number;
  blocked: number;
  rate_limited: number;
  retried: number;
  skipped: number;
  remaining: number;
  campaign_status: BroadcastCampaignStatus;
}

export interface BroadcastDelivery {
  id: number;
  campaign_id: number;
  user_id: number | null;
  subscription_id: number;
  telegram_chat_id_masked: string;
  status: BroadcastDeliveryStatus;
  attempt_count: number;
  next_attempt_at: string | null;
  sent_at: string | null;
  last_attempt_at: string | null;
  telegram_message_id: number | null;
  error_code: string | null;
  error_message: string | null;
  retry_after_seconds: number | null;
  created_at: string;
  updated_at: string;
}

export interface ChannelEntryConfig {
  bot_username: string;
  mini_app_direct_url: string;
  mini_app_url: string;
  start_param: string;
  short_name: string;
  has_customer_bot_token: boolean;
  setup_hint: string;
}

export interface TelegramChannel {
  id: number;
  title: string;
  chat_id: string;
  is_active: boolean;
  last_checked_at: string | null;
  last_check_status: string | null;
  last_check_error: string | null;
  created_by_user_id: number | null;
  created_at: string;
  updated_at: string;
}

export interface TelegramChannelPayload {
  title: string;
  chat_id: string;
}

export interface TelegramChannelCheckResponse {
  ok: boolean;
  chat_id: string;
  title: string | null;
  type: string | null;
  username: string | null;
  can_post_estimate: boolean | null;
  can_pin_estimate: boolean | null;
  message: string;
}

export interface ChannelEntryPreviewPayload {
  channel_id?: number | null;
  chat_id?: string | null;
  text: string;
  button_text?: string;
  button_style?: ChannelEntryButtonStyle;
  photo_paths?: string[];
}

export interface ChannelEntryPreview {
  text: string;
  button_text: string;
  button_style: ChannelEntryButtonStyle;
  button_url: string;
  photo_paths: string[];
  photo_urls: string[];
  selected_chat_id: string;
  warnings: string[];
}

export interface ChannelEntryPublishPayload extends ChannelEntryPreviewPayload {
  pin: boolean;
  disable_notification: boolean;
}

export interface TelegramChannelEntryMessage {
  id: number;
  channel_id: number | null;
  channel: TelegramChannel | null;
  chat_id: string;
  text: string;
  button_text: string;
  button_url: string;
  telegram_message_id: number | null;
  is_pinned: boolean;
  published_at: string | null;
  pinned_at: string | null;
  last_error: string | null;
  created_by_user_id: number | null;
  created_at: string;
  updated_at: string;
}

export interface ChannelEntryPublishResponse {
  ok: boolean;
  status: string;
  message: string;
  item: TelegramChannelEntryMessage;
}
