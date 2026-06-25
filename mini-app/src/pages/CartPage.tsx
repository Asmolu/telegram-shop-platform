import React from 'react';
import {
  getCart,
  getFavorites,
  getOrders,
  removeCartItem,
  removeFavorite,
  updateCartItem,
  updateCartItemSelection,
  updateCartSelection,
  validatePromoCode,
  toApiErrorMessage,
  type Cart,
  type Favorite,
  type Order,
  type Product,
  type PromoValidation,
} from '../shared/api';
import { useQuickCartPicker } from '../features/catalog/useQuickCartPicker';
import { useAuth } from '../shared/auth/AuthProvider';
import { getAuthPath, getSafeReturnTo, Link, useRouter, withReturnTo } from '../shared/router/RouterProvider';
import { EmptyState, ErrorState, InlineNotice, PageLoader, ProductCard, TopBar } from '../shared/ui';
import { formatDate, formatOrderStatus, formatPrice, getDisplayOldPrice } from '../shared/utils/format';
import { normalizeAssetUrl } from '../shared/utils/images';
import { getPromoErrorMessage, normalizePromoCode } from '../shared/utils/promo';
import { displaySize } from '../shared/utils/sizes';

type CartTab = 'favorites' | 'cart' | 'orders';

const tabs: Array<[CartTab, string]> = [
  ['favorites', 'Избранное'],
  ['cart', 'Корзина'],
  ['orders', 'Заказы'],
];

export function CartPage() {
  const { currentPath, searchParams, navigate } = useRouter();
  const { isAuthenticated } = useAuth();
  const activeTab = (searchParams.get('tab') as CartTab | null) ?? 'cart';
  const returnToParam = searchParams.get('returnTo');
  const returnTo = getSafeReturnTo(returnToParam);
  const [cart, setCart] = React.useState<Cart | null>(null);
  const [favorites, setFavorites] = React.useState<Favorite[]>([]);
  const [favoriteProducts, setFavoriteProducts] = React.useState<Product[]>([]);
  const [orders, setOrders] = React.useState<Order[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);
  const [notice, setNotice] = React.useState<string | null>(null);
  const [promoCode, setPromoCode] = React.useState('');
  const [promoValidation, setPromoValidation] = React.useState<PromoValidation | null>(null);

  const requireAuth = React.useCallback(() => {
    if (isAuthenticated) {
      return true;
    }
    navigate(getAuthPath(currentPath));
    return false;
  }, [currentPath, isAuthenticated, navigate]);
  const quickCart = useQuickCartPicker({
    requireAuth,
    onNotice: setNotice,
  });

  const load = React.useCallback(async () => {
    if (!isAuthenticated) {
      setLoading(false);
      return;
    }

    setLoading(true);
    setError(null);
    try {
      const [cartResult, favoriteResult, orderResult] = await Promise.all([getCart(), getFavorites(), getOrders()]);

      setCart(cartResult);
      setFavorites(favoriteResult.items);
      setFavoriteProducts(
        favoriteResult.items
          .map((favorite) => favorite.product)
          .filter((product): product is Product => Boolean(product)),
      );
      setOrders(orderResult.items);
    } catch (loadError) {
      setError(toApiErrorMessage(loadError));
    } finally {
      setLoading(false);
    }
  }, [isAuthenticated]);

  React.useEffect(() => {
    void load();
  }, [load]);

  async function changeQuantity(itemId: number, quantity: number) {
    if (quantity < 1) return;
    try {
      const appliedPromoCode = promoValidation?.code;
      const nextCart = await updateCartItem(itemId, quantity);
      setCart(nextCart);
      if (appliedPromoCode && nextCart.selected_distinct_item_count > 0) {
        await refreshPromoValidation(appliedPromoCode);
      } else if (nextCart.items.length === 0 || nextCart.selected_distinct_item_count === 0) {
        clearPromo();
      }
      window.dispatchEvent(new Event('miniapp:cart-updated'));
    } catch (actionError) {
      setNotice(toApiErrorMessage(actionError));
    }
  }

  async function removeItem(itemId: number) {
    try {
      const appliedPromoCode = promoValidation?.code;
      const nextCart = await removeCartItem(itemId);
      setCart(nextCart);
      if (appliedPromoCode && nextCart.selected_distinct_item_count > 0) {
        await refreshPromoValidation(appliedPromoCode);
      } else if (nextCart.items.length === 0 || nextCart.selected_distinct_item_count === 0) {
        clearPromo();
      }
      window.dispatchEvent(new Event('miniapp:cart-updated'));
    } catch (actionError) {
      setNotice(toApiErrorMessage(actionError));
    }
  }

  async function changeItemSelection(itemId: number, isSelected: boolean) {
    try {
      const appliedPromoCode = promoValidation?.code;
      const nextCart = await updateCartItemSelection(itemId, isSelected);
      setCart(nextCart);
      if (appliedPromoCode && nextCart.selected_distinct_item_count > 0) {
        await refreshPromoValidation(appliedPromoCode);
      } else if (nextCart.selected_distinct_item_count === 0) {
        clearPromo();
      }
    } catch (actionError) {
      setNotice(toApiErrorMessage(actionError));
    }
  }

  async function changeAllSelection(isSelected: boolean) {
    try {
      const appliedPromoCode = promoValidation?.code;
      const nextCart = await updateCartSelection(isSelected);
      setCart(nextCart);
      if (appliedPromoCode && nextCart.selected_distinct_item_count > 0) {
        await refreshPromoValidation(appliedPromoCode);
      } else if (nextCart.selected_distinct_item_count === 0) {
        clearPromo();
      }
    } catch (actionError) {
      setNotice(toApiErrorMessage(actionError));
    }
  }

  async function removeFavoriteProduct(productId: number) {
    try {
      await removeFavorite(productId);
      setFavorites((current) => current.filter((favorite) => favorite.product_id !== productId));
      setFavoriteProducts((current) => current.filter((product) => product.id !== productId));
    } catch (actionError) {
      setNotice(toApiErrorMessage(actionError));
    }
  }

  async function applyPromo(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setPromoValidation(null);
    if (!cart || cart.selected_distinct_item_count === 0) {
      setNotice('Выберите товары для оформления.');
      return;
    }
    const code = normalizePromoCode(promoCode);
    if (!code) {
      return;
    }

    try {
      const result = await validatePromoCode(code);
      setPromoValidation(result);
      setPromoCode(result.code);
      setNotice('Промокод применен.');
    } catch (promoError) {
      setNotice(getPromoErrorMessage(promoError));
    }
  }

  async function refreshPromoValidation(code: string) {
    try {
      const result = await validatePromoCode(code);
      setPromoValidation(result);
      setPromoCode(result.code);
    } catch (promoError) {
      setPromoValidation(null);
      setNotice(getPromoErrorMessage(promoError));
    }
  }

  function updatePromoCode(value: string) {
    setPromoCode(value);
    if (!value.trim() || normalizePromoCode(value) !== promoValidation?.code) {
      setPromoValidation(null);
      setNotice(null);
    }
  }

  function clearPromo() {
    setPromoCode('');
    setPromoValidation(null);
    setNotice(null);
  }

  function checkoutWithPromo() {
    if (!cart || cart.selected_distinct_item_count === 0) {
      setNotice('Выберите товары для оформления.');
      return;
    }
    const checkoutPath = promoValidation?.code
      ? `/checkout?promo_code=${encodeURIComponent(promoValidation.code)}`
      : '/checkout';
    navigate(withReturnTo(checkoutPath, returnToParam));
  }

  if (!isAuthenticated) {
    return (
      <div className="page page--gradient-header">
        <TopBar title="Покупки" variant="marketplace" />
        <UnauthorizedBlock onAuth={() => navigate(getAuthPath(currentPath))} />
      </div>
    );
  }

  return (
    <div className="page page--gradient-header">
      <TopBar title="Покупки" variant="marketplace" />
      <div className="tab-row cart-tabs">
        {tabs.map(([value, label]) => (
          <button
            className={activeTab === value ? 'is-selected' : ''}
            key={value}
            type="button"
            onClick={() => navigate(withReturnTo(`/cart?tab=${value}`, returnToParam))}
          >
            {label}
          </button>
        ))}
      </div>

      {notice ? (
        <InlineNotice tone={notice.includes('применен') || notice.includes('добавлен') ? 'success' : 'warning'}>
          <span>{notice}</span>
          <button type="button" onClick={() => setNotice(null)}>×</button>
        </InlineNotice>
      ) : null}

      {loading ? <PageLoader text="Загружаем покупки..." /> : null}
      {!loading && error ? <ErrorState message={error} actionLabel="Повторить" onAction={() => void load()} /> : null}
      {!loading && !error && activeTab === 'favorites' ? (
        <FavoritesTab
          products={favoriteProducts}
          favorites={favorites}
          onAddToCart={quickCart.addToCart}
          onRemove={removeFavoriteProduct}
        />
      ) : null}
      {!loading && !error && activeTab === 'cart' ? (
        <CartItemsTab
          cart={cart}
          promoCode={promoCode}
          promoValidation={promoValidation}
          onApplyPromo={applyPromo}
          onCheckout={checkoutWithPromo}
          onClearPromo={clearPromo}
          onItemSelectionChange={changeItemSelection}
          onPromoCodeChange={updatePromoCode}
          onQuantityChange={changeQuantity}
          onGoShop={() => navigate(returnTo)}
          onRemove={removeItem}
          onSelectAll={changeAllSelection}
        />
      ) : null}
      {!loading && !error && activeTab === 'orders' ? <OrdersTab orders={orders} /> : null}
      {quickCart.picker}
    </div>
  );
}

function UnauthorizedBlock({ onAuth }: { onAuth: () => void }) {
  return (
    <EmptyState
      title="Нужен вход через Telegram"
      message="Избранное, корзина и заказы доступны после входа. В браузере можно использовать тестовый код доступа."
      actionLabel="Войти"
      onAction={onAuth}
    />
  );
}

function FavoritesTab({
  products,
  favorites,
  onAddToCart,
  onRemove,
}: {
  products: Product[];
  favorites: Favorite[];
  onAddToCart: (product: Product) => Promise<void>;
  onRemove: (productId: number) => Promise<void>;
}) {
  const { navigate } = useRouter();

  if (products.length === 0) {
    return (
      <EmptyState
        title="В избранном пока пусто"
        actionLabel="Перейти к товарам"
        onAction={() => navigate('/main')}
      />
    );
  }

  const favoriteIds = new Set(favorites.map((favorite) => favorite.product_id));

  return (
    <div className="product-grid">
      {products.map((product) => (
        <ProductCard
          favorite={favoriteIds.has(product.id)}
          key={product.id}
          product={product}
          onAddToCart={onAddToCart}
          onFavoriteToggle={() => onRemove(product.id)}
        />
      ))}
    </div>
  );
}

function cartProductImageSrcSet(thumbnailUrl?: string | null, imageUrl?: string | null) {
  const normalizedThumbnail = normalizeAssetUrl(thumbnailUrl);
  const normalizedImage = normalizeAssetUrl(imageUrl);
  const entries: string[] = [];

  if (normalizedThumbnail) {
    entries.push(`${normalizedThumbnail} 240w`);
  }
  if (normalizedImage && normalizedImage !== normalizedThumbnail) {
    entries.push(`${normalizedImage} 480w`);
  }

  return entries.length > 1 ? entries.join(', ') : undefined;
}

function CartItemsTab({
  cart,
  promoCode,
  promoValidation,
  onApplyPromo,
  onCheckout,
  onClearPromo,
  onItemSelectionChange,
  onPromoCodeChange,
  onQuantityChange,
  onGoShop,
  onRemove,
  onSelectAll,
}: {
  cart: Cart | null;
  promoCode: string;
  promoValidation: PromoValidation | null;
  onApplyPromo: (event: React.FormEvent<HTMLFormElement>) => void;
  onCheckout: () => void;
  onClearPromo: () => void;
  onItemSelectionChange: (itemId: number, isSelected: boolean) => Promise<void>;
  onPromoCodeChange: (value: string) => void;
  onQuantityChange: (itemId: number, quantity: number) => Promise<void>;
  onGoShop: () => void;
  onRemove: (itemId: number) => Promise<void>;
  onSelectAll: (isSelected: boolean) => Promise<void>;
}) {
  const items = cart?.items ?? [];
  const selectedItems = items.filter((item) => item.is_selected);
  const allSelected = items.length > 0 && selectedItems.length === items.length;
  const selectedTotal = cart?.selected_total ?? '0';
  const selectedQuantity = cart?.selected_quantity_total ?? 0;

  if (!cart || items.length === 0) {
    return <EmptyState title="Корзина пустая" actionLabel="Перейти к товарам" onAction={onGoShop} />;
  }

  return (
    <div className="cart-layout">
      <div className="cart-selection-toolbar">
        <label>
          <input
            checked={allSelected}
            type="checkbox"
            onChange={(event) => void onSelectAll(event.target.checked)}
          />
          <span>Все</span>
        </label>
        <strong>{selectedQuantity} выбрано</strong>
      </div>

      <div className="cart-list">
        {items.map((item) => {
          const imageUrl = normalizeAssetUrl(item.product.thumbnail_image_url ?? item.product.image_url);
          const unavailable = item.product.status !== 'ACTIVE' || !item.product_variant.is_active || item.product_variant.available_quantity < item.quantity;
          const brand = item.product.brand?.trim() || 'MENS STYLE';
          const sizeLabel = displaySize(item.product.size_grid, item.product_variant.size, true);
          const variantInfo = [
            sizeLabel,
            item.product_variant.color,
            item.product_variant.sku ? `арт. ${item.product_variant.sku}` : '',
          ].filter(Boolean).join(' · ');
          const oldPrice = getDisplayOldPrice(
            item.unit_price,
            item.product.old_price,
            item.product.compare_at_price,
          );

          return (
            <article className={`cart-item ${item.is_selected ? '' : 'cart-item--unselected'}`} key={item.id}>
              <label className="cart-item__selector" aria-label="Выбрать товар">
                <input
                  checked={item.is_selected}
                  type="checkbox"
                  onChange={(event) => void onItemSelectionChange(item.id, event.target.checked)}
                />
              </label>
              <span className="cart-item__image">
                {imageUrl ? (
                  <img
                    src={imageUrl}
                    srcSet={cartProductImageSrcSet(item.product.thumbnail_image_url, item.product.image_url)}
                    sizes="96px"
                    alt=""
                    width={96}
                    height={120}
                    loading="lazy"
                    decoding="async"
                  />
                ) : <span>{item.product.name[0]}</span>}
              </span>
              <div className="cart-item__content">
                <div className="cart-item__price-row">
                  <strong>{formatPrice(item.unit_price)}</strong>
                  {oldPrice ? <del>{formatPrice(oldPrice)}</del> : null}
                </div>
                <span className="cart-item__brand">{brand}</span>
                <strong className="cart-item__title">{item.product.name}</strong>
                <small className="cart-item__variant">{variantInfo}</small>
                {unavailable ? <em>Проверьте наличие</em> : null}
                <small className="cart-item__delivery">Доступно к оформлению</small>
              </div>
              <div className="cart-item__actions">
                <div className="quantity-stepper" aria-label="Количество">
                  <button type="button" onClick={() => void onQuantityChange(item.id, item.quantity - 1)}>−</button>
                  <span>{item.quantity}</span>
                  <button type="button" onClick={() => void onQuantityChange(item.id, item.quantity + 1)}>+</button>
                </div>
                <button className="cart-item__buy-button" type="button" disabled={!item.is_selected || unavailable} onClick={onCheckout}>
                  Купить
                </button>
              </div>
              <button className="icon-button" type="button" onClick={() => void onRemove(item.id)} aria-label="Удалить">
                ×
              </button>
            </article>
          );
        })}
      </div>

      <form className="promo-form" onSubmit={onApplyPromo}>
        <input value={promoCode} onChange={(event) => onPromoCodeChange(event.target.value)} placeholder="Введите промокод" />
        <button className="secondary-button" type="submit" disabled={!promoCode.trim()}>
          Применить
        </button>
      </form>
      {promoValidation ? (
        <div className="promo-status promo-status--success">
          <span>{promoValidation.code}: −{formatPrice(promoValidation.discount_amount)}</span>
          <button type="button" onClick={onClearPromo}>Убрать</button>
        </div>
      ) : null}

      <section className="summary-card">
        <div><span>Выбрано</span><strong>{selectedQuantity}</strong></div>
        <div><span>Товары</span><strong>{formatPrice(selectedTotal)}</strong></div>
        <div><span>Скидка</span><strong>{formatPrice(promoValidation?.discount_amount ?? 0)}</strong></div>
        <div className="summary-card__total"><span>Итого</span><strong>{formatPrice(promoValidation?.total_amount ?? selectedTotal)}</strong></div>
        <button className="primary-button" type="button" disabled={selectedQuantity === 0} onClick={onCheckout}>
          {selectedQuantity > 0 ? `К оформлению · ${selectedQuantity}` : 'Выберите товары'}
        </button>
      </section>
    </div>
  );
}

function OrdersTab({ orders }: { orders: Order[] }) {
  const { navigate } = useRouter();

  if (orders.length === 0) {
    return <EmptyState title="Заказов пока нет" message="Оформленные покупки появятся здесь." />;
  }

  return (
    <div className="order-list">
      {orders.map((order) => {
        const promoCode = order.promo_code_code ?? order.promo_code;
        const discountAmount = Number(order.discount_amount ?? order.discount ?? 0);
        const paymentStatus = order.manual_payment?.status;
        const displayStatus = paymentStatus
          ? formatPaymentStatus(paymentStatus)
          : formatOrderStatus(order.status);
        const statusClass = paymentStatus?.toLowerCase() ?? order.status.toLowerCase();

        return (
          <article className="order-card order-card--rich" key={order.id}>
            <header className="order-card__header">
              <div>
                <strong>Заказ {order.order_number}</strong>
                <small>{formatDate(order.created_at)} · {order.items.length} поз.</small>
              </div>
              <span className={`status-pill status-pill--${statusClass}`}>
                {displayStatus}
              </span>
            </header>

            <div className="order-card__totals">
              <span>Итого</span>
              <strong>{formatPrice(order.total_amount ?? order.total)}</strong>
              {discountAmount > 0 ? (
                <>
                  <span>{promoCode ? `Промокод ${promoCode}` : 'Скидка'}</span>
                  <strong>−{formatPrice(discountAmount)}</strong>
                </>
              ) : null}
            </div>

            <div className="order-item-list">
              {order.items.map((item) => {
                const thumbnailUrl = normalizeAssetUrl(item.product_thumbnail_url || item.product_thumbnail_path);
                const variant = [
                  displaySize(item.variant_size_grid, item.variant_size, true),
                  item.variant_color,
                  item.variant_sku ? `SKU ${item.variant_sku}` : '',
                ].filter(Boolean).join(' · ');

                return (
                  <div className="order-item-row" key={item.id}>
                    <Link className="order-item-row__image" to={`/product/${item.product_id}`}>
                      {thumbnailUrl ? (
                        <img
                          src={thumbnailUrl}
                          alt=""
                          width={72}
                          height={90}
                          loading="lazy"
                          decoding="async"
                        />
                      ) : <span>{item.product_name.slice(0, 1)}</span>}
                    </Link>
                    <div>
                      <Link to={`/product/${item.product_id}`}>{item.product_title ?? item.product_name}</Link>
                      <small>{variant}</small>
                      <small>{item.quantity} × {formatPrice(item.unit_price)}</small>
                    </div>
                    <strong>{formatPrice(item.item_total ?? item.subtotal)}</strong>
                  </div>
                );
              })}
            </div>

            <button
              className="secondary-button"
              type="button"
              onClick={() =>
                navigate(
                  order.manual_payment && paymentStatus !== 'APPROVED'
                    ? `/payment/${order.id}`
                    : `/order-success/${order.id}`,
                )
              }
            >
              Подробнее
            </button>
          </article>
        );
      })}
    </div>
  );
}

function formatPaymentStatus(status: NonNullable<Order['manual_payment']>['status']) {
  const labels = {
    PENDING: 'Ожидает оплату',
    SUBMITTED: 'Оплата на проверке',
    APPROVED: 'Оплачено',
    REJECTED: 'Отклонено',
    EXPIRED: 'Время оплаты истекло',
    CANCELLED: 'Отменено',
  };
  return labels[status];
}
