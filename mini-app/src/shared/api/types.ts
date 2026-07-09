export type PageMeta = {
  limit: number;
  offset: number;
  total?: number | null;
};

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
export type ProductSearchSuggestionKind = 'product' | 'brand' | 'alias' | 'category' | 'tag';
export type ProductResolveVariantStatus =
  | 'selected'
  | 'out_of_stock'
  | 'sku_missing'
  | 'sku_not_found'
  | 'sku_not_for_product'
  | 'inactive';
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
export type DiscountType = 'PERCENT' | 'FIXED';
export type UserRole = 'USER' | 'SELLER' | 'ADMIN';
export type BannerTargetType = 'product' | 'category' | 'promo' | 'external_url';
export type BannerDisplayType = 'horizontal' | 'vertical' | 'popup' | 'aggressive_popup';

export type Category = {
  id: number;
  name: string;
  slug: string;
  description?: string | null;
  image_path?: string | null;
  image_url?: string | null;
  created_at: string;
  updated_at: string;
};

export type Tag = {
  id: number;
  name: string;
  slug: string;
  image_path?: string | null;
  image_url?: string | null;
  created_at: string;
  updated_at: string;
};

export type ProductImage = {
  id: number;
  product_id?: number;
  file_path?: string | null;
  url?: string | null;
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
  alt_text?: string | null;
  position: number;
  is_primary: boolean;
  original_filename?: string | null;
  mime_type?: string | null;
  size_bytes?: number | null;
  created_at: string;
};

export type ProductVariant = {
  id: number;
  product_id?: number;
  size: string;
  color?: string | null;
  sku?: string;
  stock_quantity?: number;
  reserved_quantity?: number;
  available_quantity: number;
  is_active: boolean;
  created_at?: string;
  updated_at?: string;
};

export type ProductCategoryAssignment = {
  category_id: number;
  priority: 1 | 2 | 3;
  category?: Category | null;
};

export type Product = {
  id: number;
  name: string;
  slug: string;
  brand?: string | null;
  description?: string | null;
  base_price: string;
  old_price?: string | null;
  compare_at_price?: string | null;
  size_grid: ProductSizeGrid;
  size_group?: ProductSizeGroup;
  image_badge_type: ProductImageBadgeType;
  image_badge_text?: string | null;
  image_badge_color?: ProductImageBadgeColor | null;
  image_badge_position?: ProductImageBadgePosition | null;
  image_url?: string | null;
  thumbnail_image_url?: string | null;
  image_width?: number | null;
  image_height?: number | null;
  status?: ProductStatus;
  category_id?: number | null;
  category?: Category | null;
  categories?: ProductCategoryAssignment[];
  tags?: Tag[];
  images?: ProductImage[];
  variants: ProductVariant[];
  related_product_ids?: number[];
  related_products?: Product[];
  is_available: boolean;
  rating?: number | string | null;
  average_rating?: number | string | null;
  review_count?: number | string | null;
  reviews_count?: number | string | null;
  rating_count?: number | string | null;
  created_at: string;
  updated_at?: string;
};

export type ProductList = {
  items: Product[];
  meta: PageMeta;
};

export type ProductResolveRouteContext = {
  category?: Pick<Category, 'id' | 'slug' | 'name'> | null;
  product_slug: string;
  requested_sku?: string | null;
  selected_variant_id?: number | null;
  selected_variant_sku?: string | null;
  variant_status?: ProductResolveVariantStatus | null;
};

export type ProductResolveResponse = {
  product: Product;
  route_context: ProductResolveRouteContext;
};

export type ProductSearchSuggestion = {
  value: string;
  kind: ProductSearchSuggestionKind;
  label?: string | null;
};

export type ProductSearchSuggestionList = {
  items: ProductSearchSuggestion[];
};

export type Banner = {
  id: number;
  image_path: string;
  image_url: string;
  target_type: BannerTargetType;
  target_id?: number | null;
  external_url?: string | null;
  promo_code?: string | null;
  display_type: BannerDisplayType;
  position: number;
};

export type BannerList = {
  items: Banner[];
  meta: PageMeta;
};

export type LookStatus = 'DRAFT' | 'ACTIVE' | 'ARCHIVED';

export type LookImage = {
  id: number;
  look_id: number;
  file_path: string;
  url: string;
  image_url?: string | null;
  original_filename?: string | null;
  mime_type?: string | null;
  size_bytes?: number | null;
  alt_text?: string | null;
  position: number;
  is_primary: boolean;
  created_at: string;
};

export type LookProductSummary = {
  product_id: number;
  product_slug: string;
  name: string;
  brand?: string | null;
  image_url?: string | null;
  price: string | number;
  old_price?: string | number | null;
};

export type LookItem = {
  look_item_id: number;
  product: LookProductSummary;
  product_id: number;
  product_slug: string;
  product_name: string;
  brand?: string | null;
  primary_image_url?: string | null;
  price: string | number;
  old_price?: string | number | null;
  quantity: number;
  is_default_selected: boolean;
  size_group: ProductSizeGroup;
  available_sizes: string[];
  one_size: boolean;
  is_available: boolean;
};

export type LookCard = {
  id: number;
  slug: string;
  title: string;
  description?: string | null;
  primary_image_url?: string | null;
  price: string | number;
  old_price?: string | number | null;
  item_count: number;
  default_selected_item_ids: number[];
  is_available: boolean;
  available_sizes: string[];
  available_clothing_sizes: string[];
  available_footwear_sizes: string[];
  requires_clothing_size: boolean;
  requires_footwear_size: boolean;
};

export type LookList = {
  items: LookCard[];
  meta: PageMeta;
};

export type FeedProductItem = {
  type: 'product';
  product: Product;
};

export type FeedLookItem = {
  type: 'look';
  look: LookCard;
};

export type FeedItem = FeedProductItem | FeedLookItem;

export type FeedList = {
  items: FeedItem[];
  meta: PageMeta;
};

export type LookDetail = {
  id: number;
  slug: string;
  title: string;
  description?: string | null;
  images: LookImage[];
  items: LookItem[];
  default_selected_item_ids: number[];
  default_price: string | number;
  old_price?: string | number | null;
  available_sizes: string[];
  available_clothing_sizes: string[];
  available_footwear_sizes: string[];
  requires_clothing_size: boolean;
  requires_footwear_size: boolean;
  is_available: boolean;
};

export type LookCartPayload = {
  selected_item_ids: number[];
  size?: string | null;
  clothing_size?: string | null;
  footwear_size?: string | null;
};

export type LookCartResponse = {
  message: string;
  cart: Cart;
};

export type User = {
  id: number;
  telegram_id: number;
  username?: string | null;
  first_name?: string | null;
  last_name?: string | null;
  phone?: string | null;
  role: UserRole;
  is_active: boolean;
  created_at: string;
  updated_at: string;
};

export type PersonalData = {
  recipient_name?: string | null;
  contact_phone?: string | null;
  city?: string | null;
  height_cm?: number | null;
  weight_kg?: string | number | null;
  telegram_username?: string | null;
  persistent_comment?: string | null;
};

export type PersonalDataUpdate = PersonalData;

export type TokenResponse = {
  access_token: string;
  token_type: 'bearer' | string;
  user: User;
};

export type CartProduct = {
  id: number;
  name: string;
  slug: string;
  brand?: string | null;
  base_price: string;
  old_price?: string | null;
  compare_at_price?: string | null;
  size_grid: ProductSizeGrid;
  status: ProductStatus;
  image_url?: string | null;
  thumbnail_image_url?: string | null;
};

export type CartProductVariant = {
  id: number;
  product_id: number;
  size: string;
  color?: string | null;
  sku: string;
  is_active: boolean;
  available_quantity: number;
};

export type CartItem = {
  id: number;
  product: CartProduct;
  product_variant: CartProductVariant;
  quantity: number;
  is_selected: boolean;
  unit_price: string;
  subtotal: string;
  source_type?: ItemSourceType | null;
  source_group_id?: string | null;
  source_look_id?: number | null;
  source_look_slug?: string | null;
  source_look_title?: string | null;
  source_look_image_url?: string | null;
  created_at: string;
  updated_at: string;
};

export type Cart = {
  id: number;
  user_id: number;
  items: CartItem[];
  total: string;
  quantity_total: number;
  distinct_item_count: number;
  selected_total: string;
  selected_quantity_total: number;
  selected_distinct_item_count: number;
  created_at: string;
  updated_at: string;
};

export type Favorite = {
  id: number;
  user_id: number;
  product_id: number;
  product?: Product | null;
  created_at: string;
};

export type FavoriteList = {
  items: Favorite[];
};

export type PromoValidation = {
  code: string;
  discount_type: DiscountType;
  discount_value: string;
  subtotal_amount: string;
  discount_amount: string;
  total_amount: string;
};

export type OrderItem = {
  id: number;
  product_id: number;
  product_variant_id: number;
  product_name: string;
  product_brand?: string | null;
  variant_size: string;
  variant_size_grid: ProductSizeGrid;
  variant_color?: string | null;
  variant_sku: string;
  unit_price: string;
  quantity: number;
  subtotal: string;
  is_returnable: boolean;
  product_title?: string;
  item_total?: string;
  product_thumbnail_path?: string | null;
  product_thumbnail_url?: string | null;
  source_type?: ItemSourceType | null;
  source_group_id?: string | null;
  source_look_id?: number | null;
  source_look_slug?: string | null;
  source_look_title?: string | null;
  source_look_image_url?: string | null;
  created_at: string;
};

export type Order = {
  id: number;
  order_number: string;
  user_id: number;
  status: OrderStatus;
  subtotal_amount: string;
  discount_amount: string;
  promo_code_id?: number | null;
  promo_code_code?: string | null;
  promo_code?: string | null;
  promo_applied?: boolean;
  total_amount: string;
  delivery_price?: string;
  subtotal?: string;
  discount?: string;
  total?: string;
  contact_name: string;
  contact_phone: string;
  delivery_method?: OrderDeliveryMethod | null;
  delivery_address: string;
  delivery_comment?: string | null;
  manual_payment?: {
    id: number;
    status: ManualPaymentStatus;
    expires_at: string;
    submitted_at?: string | null;
    receipt_image_path?: string | null;
    receipt_image_url?: string | null;
  } | null;
  items: OrderItem[];
  delivered_at?: string | null;
  created_at: string;
  updated_at: string;
};

export type OrderList = {
  items: Order[];
};

export type PaymentSuccessBannerPending = {
  order_id: number;
  order_number: string;
  image_path: string;
  image_url: string;
  created_at: string;
  total_amount: string;
  delivery_method?: OrderDeliveryMethod | null;
  payment_status: ManualPaymentStatus;
};

export type PaymentSuccessBannerSeen = {
  order_id: number;
  seen_at: string;
};

export type ReturnRequestStatus =
  | 'PENDING'
  | 'APPROVED'
  | 'REJECTED'
  | 'COMPLETED'
  | 'CANCELLED';

export type ReturnEligibilityItem = {
  order_item_id: number;
  product_name: string;
  product_brand?: string | null;
  image_url?: string | null;
  sku?: string | null;
  size?: string | null;
  color?: string | null;
  quantity: number;
  is_returnable: boolean;
  eligible: boolean;
  ineligible_reason?: string | null;
};

export type ReturnEligibility = {
  eligible: boolean;
  reason_code?: string | null;
  message: string;
  return_window_until?: string | null;
  order_id: number;
  return_request_id?: number | null;
  items: ReturnEligibilityItem[];
};

export type ReturnRequestItemPayload = {
  order_item_id: number;
  quantity: number;
};

export type ReturnRequestPayload = {
  reason: string;
  comment?: string | null;
  items: ReturnRequestItemPayload[];
};

export type ReturnRequestItem = {
  id: number;
  order_item_id: number;
  product_id?: number | null;
  product_variant_id?: number | null;
  product_name: string;
  product_brand?: string | null;
  sku?: string | null;
  size?: string | null;
  color?: string | null;
  unit_price: string;
  quantity: number;
  created_at: string;
};

export type ReturnRequestAttachment = {
  id: number;
  file_path: string;
  original_filename: string;
  mime_type: string;
  size_bytes: number;
  media_type: 'image' | 'video';
  position: number;
  url: string;
  created_at: string;
};

export type ReturnRequest = {
  id: number;
  return_number: string;
  order_id: number;
  order_number?: string | null;
  user_id: number;
  status: ReturnRequestStatus;
  reason: string;
  comment?: string | null;
  items: ReturnRequestItem[];
  attachments: ReturnRequestAttachment[];
  decided_at?: string | null;
  decided_by_user_id?: number | null;
  decision_comment?: string | null;
  completed_at?: string | null;
  completed_by_user_id?: number | null;
  completion_comment?: string | null;
  cancelled_at?: string | null;
  cancelled_by_user_id?: number | null;
  cancellation_comment?: string | null;
  message?: string | null;
  created_at: string;
  updated_at: string;
};

export type ManualPayment = {
  id: number;
  order_id: number;
  order_number: string;
  order_status: OrderStatus;
  customer_user_id: number;
  customer_name: string;
  customer_phone: string;
  delivery_method?: OrderDeliveryMethod | null;
  delivery_price?: string | number;
  method: 'SBP_PHONE';
  amount: string;
  currency: 'RUB';
  status: ManualPaymentStatus;
  expires_at: string;
  server_now: string;
  seller_phone_display: string;
  seller_phone_e164: string;
  seller_bank_name?: string | null;
  seller_recipient_name?: string | null;
  payment_comment: string;
  receipt_image_path?: string | null;
  receipt_image_url?: string | null;
  submitted_at?: string | null;
  approved_at?: string | null;
  rejected_at?: string | null;
  reject_reason?: string | null;
  stock_released_at?: string | null;
  created_at: string;
  updated_at: string;
};

export type Review = {
  id: number;
  user_id: number;
  product_id: number;
  order_id?: number | null;
  rating: number;
  text: string;
  status: ReviewStatus;
  moderated_at?: string | null;
  moderated_by_id?: number | null;
  created_at: string;
  updated_at: string;
};

export type ReviewList = {
  items: Review[];
};

export type CheckoutPayload = {
  contact_name: string;
  contact_phone: string;
  delivery_method: OrderDeliveryMethod;
  delivery_address: string;
  delivery_comment?: string | null;
  promo_code?: string | null;
};

export type CustomerNotificationSubscription = {
  has_chat: boolean;
  write_access_granted?: boolean;
  service_notifications_available?: boolean;
  availability_status?: string;
  availability_reason?: string | null;
  service_opt_in: boolean;
  marketing_opt_in: boolean;
  blocked_at?: string | null;
  write_access_granted_at?: string | null;
  write_access_denied_at?: string | null;
  telegram_username?: string | null;
  bot_start_link?: string | null;
  start_command: string;
};

export type CustomerNotificationSubscriptionUpdate = {
  service_opt_in?: boolean;
  marketing_opt_in?: boolean;
};

export type CustomerNotificationWriteAccessRequest = {
  granted: boolean;
  source?: string;
};

export type CustomerNotificationStartLink = {
  bot_start_link?: string | null;
  start_command: string;
};

export type SellerContactSettings = {
  telegram_url?: string | null;
  whatsapp_url?: string | null;
  instagram_url?: string | null;
  updated_at?: string | null;
};
