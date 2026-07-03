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
  type CartItem,
  type Favorite,
  type Order,
  type Product,
  type PromoValidation,
} from '../shared/api';
import { useQuickCartPicker } from '../features/catalog/useQuickCartPicker';
import { useAuth } from '../shared/auth/AuthProvider';
import { getAuthPath, getSafeReturnTo, Link, useRouter, withReturnTo } from '../shared/router/RouterProvider';
import { EmptyState, ErrorState, InlineNotice, LookSourceHeader, PageLoader, ProductCard, TopBar } from '../shared/ui';
import { getTelegramWebApp } from '../shared/telegram/webApp';
import { formatDate, formatOrderStatus, formatPrice, getDisplayOldPrice } from '../shared/utils/format';
import { normalizeAssetUrl } from '../shared/utils/images';
import { getMotionAwareScrollBehavior } from '../shared/utils/motion';
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

function isLookSourceItem(item: CartItem | Order['items'][number]) {
  return item.source_type === 'LOOK' && Boolean(item.source_group_id);
}

function lookSourceLabelTitle(item: CartItem | Order['items'][number]) {
  return item.source_look_title?.trim() || 'Образ';
}

function cartLookGroupSubtotal(items: CartItem[]) {
  return items.reduce((total, item) => total + Number(item.subtotal), 0);
}

function orderLookGroupSubtotal(items: Order['items']) {
  return items.reduce((total, item) => total + Number(item.item_total ?? item.subtotal), 0);
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
  const { currentPath, navigate } = useRouter();
  const promoFormRef = React.useRef<HTMLFormElement | null>(null);
  const promoInputRef = React.useRef<HTMLInputElement | null>(null);
  const promoVisibilityTimers = React.useRef<number[]>([]);
  const promoVisibilityFrame = React.useRef<number | null>(null);
  const [promoFocused, setPromoFocused] = React.useState(false);
  const [keyboardSafeBottom, setKeyboardSafeBottom] = React.useState(0);
  const items = cart?.items ?? [];
  const selectedItems = items.filter((item) => item.is_selected);
  const allSelected = items.length > 0 && selectedItems.length === items.length;
  const selectedTotal = cart?.selected_total ?? '0';
  const selectedQuantity = cart?.selected_quantity_total ?? 0;

  const getKeyboardSafeBottom = React.useCallback(() => {
    const visualViewport = window.visualViewport;
    const visualViewportInset = visualViewport
      ? Math.max(0, window.innerHeight - visualViewport.height - visualViewport.offsetTop)
      : 0;
    const webApp = getTelegramWebApp();
    const telegramViewportInset = webApp?.viewportStableHeight && webApp.viewportHeight
      ? Math.max(0, webApp.viewportStableHeight - webApp.viewportHeight)
      : 0;

    return Math.round(Math.min(Math.max(visualViewportInset, telegramViewportInset), 420));
  }, []);

  const clearPromoVisibilityTimers = React.useCallback(() => {
    promoVisibilityTimers.current.forEach((timer) => window.clearTimeout(timer));
    promoVisibilityTimers.current = [];
    if (promoVisibilityFrame.current !== null) {
      if (typeof window.cancelAnimationFrame === 'function') {
        window.cancelAnimationFrame(promoVisibilityFrame.current);
      } else {
        window.clearTimeout(promoVisibilityFrame.current);
      }
      promoVisibilityFrame.current = null;
    }
  }, []);

  const keepPromoInputVisible = React.useCallback(() => {
    const input = promoInputRef.current;
    const target = promoFormRef.current ?? input;
    if (!input || !target) {
      return;
    }

    const behavior = getMotionAwareScrollBehavior();
    const visualViewport = window.visualViewport;
    if (!visualViewport || visualViewport.height <= 0 || typeof window.scrollTo !== 'function') {
      input.scrollIntoView({
        behavior,
        block: 'center',
        inline: 'nearest',
      });
      return;
    }

    const rect = target.getBoundingClientRect();
    const viewportTop = visualViewport.offsetTop || 0;
    const viewportHeight = visualViewport.height;
    const keyboardInset = getKeyboardSafeBottom();
    const bottomGuard = keyboardInset > 24 ? 88 : 76;
    const visibleTop = viewportTop + 12;
    const visibleBottom = viewportTop + viewportHeight - bottomGuard;
    const visibleHeight = visibleBottom - visibleTop;

    if (visibleHeight <= rect.height + 16) {
      input.scrollIntoView({
        behavior,
        block: 'center',
        inline: 'nearest',
      });
      return;
    }

    if (rect.top >= visibleTop && rect.bottom <= visibleBottom) {
      return;
    }

    const targetTop = window.scrollY + rect.top;
    const desiredTop = targetTop - viewportTop - Math.max((visibleHeight - rect.height) / 2, 0) + 6;
    window.scrollTo({
      top: Math.max(0, desiredTop),
      behavior,
    });
  }, [getKeyboardSafeBottom]);

  const queuePromoVisibility = React.useCallback(() => {
    if (promoVisibilityFrame.current !== null) {
      return;
    }

    const runVisibilityCheck = () => {
      promoVisibilityFrame.current = null;
      keepPromoInputVisible();
    };

    promoVisibilityFrame.current = typeof window.requestAnimationFrame === 'function'
      ? window.requestAnimationFrame(runVisibilityCheck)
      : window.setTimeout(runVisibilityCheck, 16);
  }, [keepPromoInputVisible]);

  const schedulePromoVisibility = React.useCallback((delays = [0, 90, 260, 520]) => {
    clearPromoVisibilityTimers();
    promoVisibilityTimers.current = delays.map((delay) =>
      window.setTimeout(queuePromoVisibility, delay),
    );
  }, [clearPromoVisibilityTimers, queuePromoVisibility]);

  React.useEffect(() => {
    if (!promoFocused) {
      return undefined;
    }

    const webApp = getTelegramWebApp();
    const handleViewportChange = () => {
      setKeyboardSafeBottom(getKeyboardSafeBottom());
      schedulePromoVisibility([0, 80, 220]);
    };

    handleViewportChange();
    window.addEventListener('resize', handleViewportChange);
    window.visualViewport?.addEventListener('resize', handleViewportChange);
    window.visualViewport?.addEventListener('scroll', handleViewportChange);
    webApp?.onEvent?.('viewportChanged', handleViewportChange);

    return () => {
      window.removeEventListener('resize', handleViewportChange);
      window.visualViewport?.removeEventListener('resize', handleViewportChange);
      window.visualViewport?.removeEventListener('scroll', handleViewportChange);
      webApp?.offEvent?.('viewportChanged', handleViewportChange);
    };
  }, [getKeyboardSafeBottom, promoFocused, schedulePromoVisibility]);

  React.useEffect(() => {
    if (!promoFocused) {
      return;
    }

    setKeyboardSafeBottom(getKeyboardSafeBottom());
    schedulePromoVisibility([0, 80, 220]);
  }, [getKeyboardSafeBottom, promoCode, promoFocused, promoValidation, schedulePromoVisibility]);

  React.useEffect(() => () => clearPromoVisibilityTimers(), [clearPromoVisibilityTimers]);

  function handlePromoFocus() {
    setPromoFocused(true);
    setKeyboardSafeBottom(getKeyboardSafeBottom());
    schedulePromoVisibility();
  }

  function handlePromoBlur() {
    setPromoFocused(false);
    setKeyboardSafeBottom(0);
    clearPromoVisibilityTimers();
  }

  function handlePromoInputChange(value: string) {
    onPromoCodeChange(value);
    if (promoFocused) {
      setKeyboardSafeBottom(getKeyboardSafeBottom());
      schedulePromoVisibility([0, 80, 220, 520, 760]);
    }
  }

  function navigateToProduct(productId: number) {
    navigate(withReturnTo(`/product/${productId}`, currentPath));
  }

  function stopCartItemNavigation(event: React.SyntheticEvent) {
    event.stopPropagation();
  }

  function handleCartItemKeyDown(event: React.KeyboardEvent<HTMLElement>, productId: number) {
    if (event.key !== 'Enter' && event.key !== ' ') {
      return;
    }

    event.preventDefault();
    navigateToProduct(productId);
  }

  if (!cart || items.length === 0) {
    return <EmptyState title="Корзина пустая" actionLabel="Перейти к товарам" onAction={onGoShop} />;
  }

  const keyboardOpen = promoFocused && keyboardSafeBottom > 24;

  return (
    <div
      className={`cart-layout ${promoFocused ? 'cart-layout--promo-focused' : ''} ${keyboardOpen ? 'cart-layout--keyboard-open' : ''}`}
      style={promoFocused ? { '--cart-keyboard-safe-bottom': `${keyboardSafeBottom}px` } as React.CSSProperties : undefined}
    >
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
        {items.map((item, index) => {
          const imageUrl = normalizeAssetUrl(item.product.thumbnail_image_url ?? item.product.image_url);
          const unavailable = item.product.status !== 'ACTIVE' || !item.product_variant.is_active || item.product_variant.available_quantity < item.quantity;
          const brand = item.product.brand?.trim() || 'ICON STORE';
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
          const lookSourceGroupId = isLookSourceItem(item) ? item.source_group_id : null;
          const previousItem = items[index - 1];
          const startsLookGroup = Boolean(
            lookSourceGroupId
            && (!previousItem
              || previousItem.source_type !== 'LOOK'
              || previousItem.source_group_id !== lookSourceGroupId),
          );
          const lookGroupItems = startsLookGroup
            ? items.filter((candidate) => (
              candidate.source_type === 'LOOK'
              && candidate.source_group_id === lookSourceGroupId
            ))
            : [];

          return (
            <React.Fragment key={item.id}>
              {startsLookGroup ? (
                <LookSourceHeader
                  imageUrl={item.source_look_image_url}
                  subtotal={cartLookGroupSubtotal(lookGroupItems)}
                  title={lookSourceLabelTitle(item)}
                />
              ) : null}
            <article
              className={`cart-item cart-item--clickable ${item.is_selected ? '' : 'cart-item--unselected'}`}
              role="link"
              tabIndex={0}
              onClick={() => navigateToProduct(item.product.id)}
              onKeyDown={(event) => handleCartItemKeyDown(event, item.product.id)}
            >
              <label
                className="cart-item__selector"
                aria-label="Выбрать товар"
                onClick={stopCartItemNavigation}
                onKeyDown={stopCartItemNavigation}
              >
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
                <div
                  className="quantity-stepper"
                  aria-label="Количество"
                  onClick={stopCartItemNavigation}
                  onKeyDown={stopCartItemNavigation}
                >
                  <button type="button" onClick={() => void onQuantityChange(item.id, item.quantity - 1)}>−</button>
                  <span>{item.quantity}</span>
                  <button type="button" onClick={() => void onQuantityChange(item.id, item.quantity + 1)}>+</button>
                </div>
                <button
                  className="cart-item__buy-button"
                  type="button"
                  disabled={!item.is_selected || unavailable}
                  onClick={(event) => {
                    stopCartItemNavigation(event);
                    onCheckout();
                  }}
                  onKeyDown={stopCartItemNavigation}
                >
                  Купить
                </button>
              </div>
              <button
                className="icon-button"
                type="button"
                onClick={(event) => {
                  stopCartItemNavigation(event);
                  void onRemove(item.id);
                }}
                onKeyDown={stopCartItemNavigation}
                aria-label="Удалить"
              >
                ×
              </button>
            </article>
            </React.Fragment>
          );
        })}
      </div>

      <form className="promo-form" data-keyboard-keep-focus ref={promoFormRef} onSubmit={onApplyPromo}>
        <input
          ref={promoInputRef}
          value={promoCode}
          onBlur={handlePromoBlur}
          onChange={(event) => handlePromoInputChange(event.target.value)}
          onFocus={handlePromoFocus}
          placeholder="Введите промокод"
        />
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
        <p className="summary-card__hint">Цена сформирована без учёта стоимости доставки.</p>
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
  const { currentPath, navigate } = useRouter();

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
              {order.items.map((item, index) => {
                const thumbnailUrl = normalizeAssetUrl(item.product_thumbnail_url || item.product_thumbnail_path);
                const productPath = withReturnTo(`/product/${item.product_id}`, currentPath);
                const lookSourceGroupId = isLookSourceItem(item) ? item.source_group_id : null;
                const previousItem = order.items[index - 1];
                const startsLookGroup = Boolean(
                  lookSourceGroupId
                  && (!previousItem
                    || previousItem.source_type !== 'LOOK'
                    || previousItem.source_group_id !== lookSourceGroupId),
                );
                const lookGroupItems = startsLookGroup
                  ? order.items.filter((candidate) => (
                    candidate.source_type === 'LOOK'
                    && candidate.source_group_id === lookSourceGroupId
                  ))
                  : [];
                const variant = [
                  displaySize(item.variant_size_grid, item.variant_size, true),
                  item.variant_color,
                  item.variant_sku ? `SKU ${item.variant_sku}` : '',
                ].filter(Boolean).join(' · ');

                return (
                  <React.Fragment key={item.id}>
                    {startsLookGroup ? (
                      <LookSourceHeader
                        imageUrl={item.source_look_image_url}
                        subtotal={orderLookGroupSubtotal(lookGroupItems)}
                        title={lookSourceLabelTitle(item)}
                      />
                    ) : null}
                  <div className="order-item-row">
                    <Link className="order-item-row__image" to={productPath}>
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
                      <Link to={productPath}>{item.product_title ?? item.product_name}</Link>
                      {item.product_brand ? <small>{item.product_brand}</small> : null}
                      <small>{variant}</small>
                      <small>{item.quantity} × {formatPrice(item.unit_price)}</small>
                    </div>
                    <strong>{formatPrice(item.item_total ?? item.subtotal)}</strong>
                  </div>
                  </React.Fragment>
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
