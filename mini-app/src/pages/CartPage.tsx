import React from 'react';
import {
  getCart,
  getFavorites,
  getOrders,
  getProduct,
  removeCartItem,
  removeFavorite,
  updateCartItem,
  validatePromoCode,
  toApiErrorMessage,
  type Cart,
  type Favorite,
  type Order,
  type Product,
  type PromoValidation,
} from '../shared/api';
import { useAuth } from '../shared/auth/AuthProvider';
import { getAuthPath, getSafeReturnTo, Link, useRouter, withReturnTo } from '../shared/router/RouterProvider';
import { EmptyState, ErrorState, InlineNotice, PageLoader, ProductCard, TopBar } from '../shared/ui';
import { formatDate, formatOrderStatus, formatPrice } from '../shared/utils/format';
import { getProductImageUrl, normalizeAssetUrl } from '../shared/utils/images';
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
  const [cartProducts, setCartProducts] = React.useState<Map<number, Product>>(new Map());
  const [orders, setOrders] = React.useState<Order[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);
  const [notice, setNotice] = React.useState<string | null>(null);
  const [promoCode, setPromoCode] = React.useState('');
  const [promoValidation, setPromoValidation] = React.useState<PromoValidation | null>(null);

  const load = React.useCallback(async () => {
    if (!isAuthenticated) {
      setLoading(false);
      return;
    }

    setLoading(true);
    setError(null);
    try {
      const [cartResult, favoriteResult, orderResult] = await Promise.all([getCart(), getFavorites(), getOrders()]);
      const favoriteProductResults = await Promise.allSettled(
        favoriteResult.items.map((favorite) => getProduct(favorite.product_id)),
      );
      const cartProductResults = await Promise.allSettled(
        cartResult.items.map((item) => getProduct(item.product.id)),
      );
      const nextCartProducts = new Map<number, Product>();
      cartProductResults.forEach((result) => {
        if (result.status === 'fulfilled') {
          nextCartProducts.set(result.value.id, result.value);
        }
      });

      setCart(cartResult);
      setFavorites(favoriteResult.items);
      setFavoriteProducts(
        favoriteProductResults
          .filter((result): result is PromiseFulfilledResult<Product> => result.status === 'fulfilled')
          .map((result) => result.value),
      );
      setCartProducts(nextCartProducts);
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
      if (appliedPromoCode && nextCart.items.length > 0) {
        await refreshPromoValidation(appliedPromoCode);
      } else if (nextCart.items.length === 0) {
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
      if (appliedPromoCode && nextCart.items.length > 0) {
        await refreshPromoValidation(appliedPromoCode);
      } else if (nextCart.items.length === 0) {
        clearPromo();
      }
      window.dispatchEvent(new Event('miniapp:cart-updated'));
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
    const checkoutPath = promoValidation?.code
      ? `/checkout?promo_code=${encodeURIComponent(promoValidation.code)}`
      : '/checkout';
    navigate(withReturnTo(checkoutPath, returnToParam));
  }

  if (!isAuthenticated) {
    return (
      <div className="page">
        <TopBar title="Покупки" />
        <UnauthorizedBlock onAuth={() => navigate(getAuthPath(currentPath))} />
      </div>
    );
  }

  return (
    <div className="page">
      <TopBar title="Покупки" />
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
        <InlineNotice tone={notice.includes('применен') ? 'success' : 'warning'}>
          <span>{notice}</span>
          <button type="button" onClick={() => setNotice(null)}>×</button>
        </InlineNotice>
      ) : null}

      {loading ? <PageLoader text="Загружаем покупки..." /> : null}
      {!loading && error ? <ErrorState message={error} actionLabel="Повторить" onAction={() => void load()} /> : null}
      {!loading && !error && activeTab === 'favorites' ? (
        <FavoritesTab products={favoriteProducts} favorites={favorites} onRemove={removeFavoriteProduct} />
      ) : null}
      {!loading && !error && activeTab === 'cart' ? (
        <CartItemsTab
          cart={cart}
          productMap={cartProducts}
          promoCode={promoCode}
          promoValidation={promoValidation}
          onApplyPromo={applyPromo}
          onCheckout={checkoutWithPromo}
          onClearPromo={clearPromo}
          onPromoCodeChange={updatePromoCode}
          onQuantityChange={changeQuantity}
          onGoShop={() => navigate(returnTo)}
          onRemove={removeItem}
        />
      ) : null}
      {!loading && !error && activeTab === 'orders' ? <OrdersTab orders={orders} /> : null}
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
  onRemove,
}: {
  products: Product[];
  favorites: Favorite[];
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
          onFavoriteToggle={() => onRemove(product.id)}
        />
      ))}
    </div>
  );
}

function CartItemsTab({
  cart,
  productMap,
  promoCode,
  promoValidation,
  onApplyPromo,
  onCheckout,
  onClearPromo,
  onPromoCodeChange,
  onQuantityChange,
  onGoShop,
  onRemove,
}: {
  cart: Cart | null;
  productMap: Map<number, Product>;
  promoCode: string;
  promoValidation: PromoValidation | null;
  onApplyPromo: (event: React.FormEvent<HTMLFormElement>) => void;
  onCheckout: () => void;
  onClearPromo: () => void;
  onPromoCodeChange: (value: string) => void;
  onQuantityChange: (itemId: number, quantity: number) => Promise<void>;
  onGoShop: () => void;
  onRemove: (itemId: number) => Promise<void>;
}) {
  const items = cart?.items ?? [];

  if (!cart || items.length === 0) {
    return <EmptyState title="Корзина пустая" actionLabel="Перейти к товарам" onAction={onGoShop} />;
  }

  return (
    <div className="cart-layout">
      <div className="cart-list">
        {items.map((item) => {
          const product = productMap.get(item.product.id);
          const imageUrl = product ? getProductImageUrl(product) : null;
          const unavailable = item.product.status !== 'ACTIVE' || !item.product_variant.is_active || item.product_variant.available_quantity < item.quantity;

          return (
            <article className="cart-item" key={item.id}>
              <span className="cart-item__image">
                {imageUrl ? <img src={imageUrl} alt="" /> : <span>{item.product.name[0]}</span>}
              </span>
              <div>
                <strong>{item.product.name}</strong>
                <small>{displaySize(item.product.size_grid, item.product_variant.size, true)}{item.product_variant.color ? ` · ${item.product_variant.color}` : ''}</small>
                {unavailable ? <em>Проверьте наличие</em> : null}
                <span>{formatPrice(item.unit_price)}</span>
              </div>
              <div className="quantity-stepper">
                <button type="button" onClick={() => void onQuantityChange(item.id, item.quantity - 1)}>−</button>
                <span>{item.quantity}</span>
                <button type="button" onClick={() => void onQuantityChange(item.id, item.quantity + 1)}>+</button>
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
        <div><span>Товары</span><strong>{formatPrice(cart.total)}</strong></div>
        <div><span>Скидка</span><strong>{formatPrice(promoValidation?.discount_amount ?? 0)}</strong></div>
        <div className="summary-card__total"><span>Итого</span><strong>{formatPrice(promoValidation?.total_amount ?? cart.total)}</strong></div>
        <button className="primary-button" type="button" onClick={onCheckout}>
          Оформить заказ
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

        return (
          <article className="order-card order-card--rich" key={order.id}>
            <header className="order-card__header">
              <div>
                <strong>Заказ {order.order_number}</strong>
                <small>{formatDate(order.created_at)} · {order.items.length} поз.</small>
              </div>
              <span className={`status-pill status-pill--${order.status.toLowerCase()}`}>
                {formatOrderStatus(order.status)}
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
                      {thumbnailUrl ? <img src={thumbnailUrl} alt="" /> : <span>{item.product_name.slice(0, 1)}</span>}
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

            <button className="secondary-button" type="button" onClick={() => navigate(`/order-success/${order.id}`)}>
              Подробнее
            </button>
          </article>
        );
      })}
    </div>
  );
}
