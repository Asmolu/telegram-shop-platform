export type PageMeta = {
  limit: number;
  offset: number;
  total?: number | null;
};

export type ProductStatus = 'DRAFT' | 'ACTIVE' | 'OUT_OF_STOCK' | 'ARCHIVED';
export type ProductSizeGrid = 'clothing_alpha' | 'shoes_ru';
export type OrderStatus = 'NEW' | 'PROCESSING' | 'SHIPPED' | 'DELIVERED' | 'CANCELLED';
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
  created_at: string;
  updated_at: string;
};

export type Tag = {
  id: number;
  name: string;
  slug: string;
  created_at: string;
  updated_at: string;
};

export type ProductImage = {
  id: number;
  product_id: number;
  file_path: string;
  url: string;
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
  product_id: number;
  size: string;
  color?: string | null;
  sku: string;
  stock_quantity: number;
  reserved_quantity: number;
  available_quantity: number;
  is_active: boolean;
  created_at: string;
  updated_at: string;
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
  description?: string | null;
  base_price: string;
  old_price?: string | null;
  compare_at_price?: string | null;
  size_grid: ProductSizeGrid;
  status: ProductStatus;
  category_id?: number | null;
  category?: Category | null;
  categories?: ProductCategoryAssignment[];
  tags: Tag[];
  images: ProductImage[];
  variants: ProductVariant[];
  is_available: boolean;
  created_at: string;
  updated_at: string;
};

export type ProductList = {
  items: Product[];
  meta: PageMeta;
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

export type TokenResponse = {
  access_token: string;
  token_type: 'bearer' | string;
  user: User;
};

export type CartProduct = {
  id: number;
  name: string;
  slug: string;
  base_price: string;
  old_price?: string | null;
  compare_at_price?: string | null;
  size_grid: ProductSizeGrid;
  status: ProductStatus;
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
  unit_price: string;
  subtotal: string;
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
  created_at: string;
  updated_at: string;
};

export type Favorite = {
  id: number;
  user_id: number;
  product_id: number;
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
  variant_size: string;
  variant_size_grid: ProductSizeGrid;
  variant_color?: string | null;
  variant_sku: string;
  unit_price: string;
  quantity: number;
  subtotal: string;
  product_title?: string;
  item_total?: string;
  product_thumbnail_path?: string | null;
  product_thumbnail_url?: string | null;
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
  subtotal?: string;
  discount?: string;
  total?: string;
  contact_name: string;
  contact_phone: string;
  delivery_address: string;
  delivery_comment?: string | null;
  items: OrderItem[];
  created_at: string;
  updated_at: string;
};

export type OrderList = {
  items: Order[];
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
  delivery_address: string;
  delivery_comment?: string | null;
  promo_code?: string | null;
};

export type CustomerNotificationSubscription = {
  has_chat: boolean;
  service_opt_in: boolean;
  marketing_opt_in: boolean;
  blocked_at?: string | null;
  telegram_username?: string | null;
  bot_start_link?: string | null;
  start_command: string;
};

export type CustomerNotificationSubscriptionUpdate = {
  service_opt_in?: boolean;
  marketing_opt_in?: boolean;
};

export type CustomerNotificationStartLink = {
  bot_start_link?: string | null;
  start_command: string;
};
