import React from 'react';
import {
  addCartItem,
  addFavorite,
  createProductReview,
  getCart,
  getFavorites,
  getProduct,
  getProductReviews,
  removeFavorite,
  toApiErrorMessage,
  type Cart,
  type Product,
  type ProductVariant,
  type Review,
} from '../shared/api';
import { useQuickCartPicker } from '../features/catalog/useQuickCartPicker';
import { useAuth } from '../shared/auth/AuthProvider';
import { getAuthPath, getNumericRouteParam, useRouter, withReturnTo } from '../shared/router/RouterProvider';
import { EmptyState, ErrorState, InlineNotice, PageLoader, ProductCard, ProductImageCarousel, TopBar } from '../shared/ui';
import { formatDate, formatDiscountPercent, formatPrice, getDisplayOldPrice } from '../shared/utils/format';
import { runLockedAction } from '../shared/utils/actionLock';
import { displaySize, sortVariants } from '../shared/utils/sizes';

const NO_COLOR_KEY = '__no_color__';

type ColorOption = {
  key: string;
  label: string;
  availableCount: number;
};

function getVariantColorKey(variant: ProductVariant) {
  return variant.color?.trim() || NO_COLOR_KEY;
}

function getVariantColorLabel(variant: ProductVariant) {
  return variant.color?.trim() || 'Без цвета';
}

function getColorOptions(variants: ProductVariant[]): ColorOption[] {
  const options = new Map<string, ColorOption>();

  variants.forEach((variant) => {
    const key = getVariantColorKey(variant);
    const option = options.get(key) ?? {
      key,
      label: getVariantColorLabel(variant),
      availableCount: 0,
    };
    option.availableCount += Math.max(variant.available_quantity, 0);
    options.set(key, option);
  });

  return Array.from(options.values());
}

function firstSelectableVariant(variants: ProductVariant[]) {
  return variants.find((variant) => variant.available_quantity > 0) ?? variants[0] ?? null;
}

export function ProductDetailPage() {
  const { currentPath, pathname, navigate } = useRouter();
  const { isAuthenticated } = useAuth();
  const productId = getNumericRouteParam(pathname, '/product/');
  const [product, setProduct] = React.useState<Product | null>(null);
  const [reviews, setReviews] = React.useState<Review[]>([]);
  const [cart, setCart] = React.useState<Cart | null>(null);
  const [addedVariantIds, setAddedVariantIds] = React.useState<Set<number>>(new Set());
  const [favorite, setFavorite] = React.useState(false);
  const [selectedVariantId, setSelectedVariantId] = React.useState<number | null>(null);
  const [selectedColorKey, setSelectedColorKey] = React.useState<string | null>(null);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);
  const [notice, setNotice] = React.useState<string | null>(null);
  const [cartAction, setCartAction] = React.useState<'buy' | 'cart' | null>(null);
  const [favoriteBusy, setFavoriteBusy] = React.useState(false);
  const [reviewText, setReviewText] = React.useState('');
  const [reviewRating, setReviewRating] = React.useState(5);
  const [reviewBusy, setReviewBusy] = React.useState(false);
  const [descriptionExpanded, setDescriptionExpanded] = React.useState(false);
  const favoriteActionLock = React.useRef({ current: false });
  const cartActionLock = React.useRef({ current: false });
  const favoriteRef = React.useRef(favorite);
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

  React.useEffect(() => {
    favoriteRef.current = favorite;
  }, [favorite]);

  React.useEffect(() => {
    let cancelled = false;

    async function load() {
      if (!productId) {
        setError('Товар не найден');
        setLoading(false);
        return;
      }

      setLoading(true);
      setError(null);
      try {
        const [productResult, reviewsResult, favoritesResult, cartResult] = await Promise.all([
          getProduct(productId),
          getProductReviews(productId).catch(() => ({ items: [] })),
          isAuthenticated ? getFavorites().catch(() => ({ items: [] })) : Promise.resolve({ items: [] }),
          isAuthenticated ? getCart().catch(() => null) : Promise.resolve(null),
        ]);

        if (!cancelled) {
          setProduct(productResult);
          setDescriptionExpanded(false);
          setReviews(reviewsResult.items);
          setFavorite(favoritesResult.items.some((item) => item.product_id === productResult.id));
          setCart(cartResult);
          setAddedVariantIds(new Set(cartResult?.items.map((item) => item.product_variant.id) ?? []));
          const activeVariants = sortVariants(
            productResult.variants.filter((variant) => variant.is_active),
            productResult.size_grid,
          );
          const activeVariant = firstSelectableVariant(activeVariants);
          setSelectedColorKey(activeVariant ? getVariantColorKey(activeVariant) : null);
          setSelectedVariantId(activeVariant?.id ?? null);
      }
      } catch (loadError) {
        if (!cancelled) {
          setError(toApiErrorMessage(loadError));
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
        }
    }

    void load();
    return () => {
      cancelled = true;
    };
  }, [isAuthenticated, productId]);

  const activeVariants = React.useMemo(
    () => product
      ? sortVariants(
          product.variants.filter((variant) => variant.is_active),
          product.size_grid,
        )
      : [],
    [product],
  );
  const colorOptions = React.useMemo(() => getColorOptions(activeVariants), [activeVariants]);
  const selectedColorVariants = React.useMemo(
    () => selectedColorKey
      ? activeVariants.filter((variant) => getVariantColorKey(variant) === selectedColorKey)
      : activeVariants,
    [activeVariants, selectedColorKey],
  );
  const selectedColorOption = colorOptions.find((option) => option.key === selectedColorKey) ?? null;
  const showColorSelector = colorOptions.length > 1
    || colorOptions.some((option) => option.key !== NO_COLOR_KEY);

  React.useEffect(() => {
    if (!product) {
      return;
    }

    if (activeVariants.length === 0) {
      if (selectedVariantId !== null) {
        setSelectedVariantId(null);
      }
      if (selectedColorKey !== null) {
        setSelectedColorKey(null);
      }
      return;
    }

    const currentVariant = activeVariants.find((variant) => variant.id === selectedVariantId) ?? null;
    const colorStillValid = Boolean(
      selectedColorKey && colorOptions.some((option) => option.key === selectedColorKey),
    );
    const nextColorKey = colorStillValid
      ? selectedColorKey
      : currentVariant
        ? getVariantColorKey(currentVariant)
        : colorOptions[0]?.key ?? null;
    const variantsForColor = nextColorKey
      ? activeVariants.filter((variant) => getVariantColorKey(variant) === nextColorKey)
      : activeVariants;
    const currentVariantStillValid = Boolean(
      currentVariant && variantsForColor.some((variant) => variant.id === currentVariant.id),
    );
    const nextVariant = currentVariantStillValid
      ? currentVariant
      : firstSelectableVariant(variantsForColor);

    if (nextColorKey !== selectedColorKey) {
      setSelectedColorKey(nextColorKey);
    }
    if ((nextVariant?.id ?? null) !== selectedVariantId) {
      setSelectedVariantId(nextVariant?.id ?? null);
    }
  }, [activeVariants, colorOptions, product, selectedColorKey, selectedVariantId]);

  const selectedVariant = product?.variants.find((variant) => variant.id === selectedVariantId) ?? null;
  const selectedVariantAvailable = Boolean(
    selectedVariant?.is_active && selectedVariant.available_quantity > 0,
  );
  const inCart = Boolean(
    selectedVariant && (
      addedVariantIds.has(selectedVariant.id)
      || cart?.items.some((item) => item.product_variant.id === selectedVariant.id)
    ),
  );
  const averageRating = reviews.length
    ? reviews.reduce((sum, review) => sum + review.rating, 0) / reviews.length
    : null;
  const purchaseActionsDisabled = Boolean(
    cartAction !== null
    || !product?.is_available
    || (selectedVariant !== null && !selectedVariantAvailable),
  );
  const cartActionDisabled = Boolean(
    cartAction !== null
    || (!inCart && (
      !product?.is_available
      || (selectedVariant !== null && !selectedVariantAvailable)
    )),
  );

  function selectColor(colorKey: string) {
    const variantsForColor = activeVariants.filter(
      (variant) => getVariantColorKey(variant) === colorKey,
    );
    const sameSizeVariant = selectedVariant
      ? variantsForColor.find(
          (variant) => variant.size === selectedVariant.size && variant.available_quantity > 0,
        )
      : null;
    const nextVariant = sameSizeVariant ?? firstSelectableVariant(variantsForColor);

    setSelectedColorKey(colorKey);
    setSelectedVariantId(nextVariant?.id ?? null);
  }

  async function toggleFavorite() {
    if (!product) return;
    if (!isAuthenticated) {
      navigate(getAuthPath(currentPath));
      return;
    }

    await runLockedAction(favoriteActionLock.current, async () => {
      const wasFavorite = favoriteRef.current;
      const nextFavorite = !wasFavorite;
      setFavorite(nextFavorite);
      favoriteRef.current = nextFavorite;
      setFavoriteBusy(true);
      setNotice(null);

      try {
        if (wasFavorite) {
          await removeFavorite(product.id);
        } else {
          await addFavorite(product.id);
        }
      } catch (actionError) {
        const serverFavoriteState = await getServerFavoriteState(product.id);
        if (
          serverFavoriteState === nextFavorite
          || (!wasFavorite && isFavoriteAlreadyExistsError(actionError))
        ) {
          setFavorite(nextFavorite);
          favoriteRef.current = nextFavorite;
          return;
        }

        setFavorite(wasFavorite);
        favoriteRef.current = wasFavorite;
        setNotice(toApiErrorMessage(actionError));
      } finally {
        setFavoriteBusy(false);
      }
    });
  }

  async function runCartAction(action: 'buy' | 'cart') {
    if (!product || !selectedVariant) {
      setNotice('Выберите доступный размер.');
      return;
    }
    if (action === 'cart' && inCart) {
      navigate('/cart?tab=cart');
      return;
    }
    if (!selectedVariantAvailable || !product.is_available) {
      setNotice('Выбранный вариант сейчас недоступен.');
      return;
    }
    if (!isAuthenticated) {
      navigate(getAuthPath(currentPath));
      return;
    }

    await runLockedAction(cartActionLock.current, async () => {
      try {
        setCartAction(action);
        if (!inCart) {
          const nextCart = await addCartItem(product.id, selectedVariant.id, 1);
          setCart(nextCart);
          setAddedVariantIds((current) => new Set(current).add(selectedVariant.id));
          window.dispatchEvent(new Event('miniapp:cart-updated'));
        }

        if (action === 'buy') {
          navigate(withReturnTo('/checkout', currentPath));
          return;
        }
        setNotice(inCart ? 'Товар уже в корзине.' : 'Товар добавлен в корзину.');
      } catch (actionError) {
        setNotice(toApiErrorMessage(actionError));
      } finally {
        setCartAction(null);
      }
    });
  }

  async function submitReview(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!product || !reviewText.trim()) return;
    if (!isAuthenticated) {
      setNotice('Отзывы доступны после входа через Telegram.');
      return;
    }

    setReviewBusy(true);
    try {
      const review = await createProductReview(product.id, reviewRating, reviewText.trim());
      setReviews((current) => [review, ...current]);
      setReviewText('');
      setReviewRating(5);
      setNotice('Отзыв отправлен. На модерации.');
    } catch (reviewError) {
      setNotice(toApiErrorMessage(reviewError));
    } finally {
      setReviewBusy(false);
    }
  }

  function changeReviewRating(nextRating: number) {
    setReviewRating(Math.min(Math.max(nextRating, 1), 5));
  }

  function handleReviewRatingKeyDown(event: React.KeyboardEvent<HTMLDivElement>) {
    if (event.key === 'ArrowRight' || event.key === 'ArrowUp') {
      event.preventDefault();
      changeReviewRating(reviewRating + 1);
      return;
    }
    if (event.key === 'ArrowLeft' || event.key === 'ArrowDown') {
      event.preventDefault();
      changeReviewRating(reviewRating - 1);
    }
  }

  if (loading) {
    return (
      <div className="page">
        <TopBar title="Товар" backFallback="/main" />
        <PageLoader text="Загружаем товар..." />
      </div>
    );
  }

  if (error || !product) {
    return (
      <div className="page">
        <TopBar title="Товар" backFallback="/main" />
        <ErrorState message={error ?? 'Товар не найден'} actionLabel="К ленте" onAction={() => navigate('/main')} />
      </div>
    );
  }

  const oldPrice = getDisplayOldPrice(product.base_price, product.old_price, product.compare_at_price);
  const discount = oldPrice ? formatDiscountPercent(product.base_price, oldPrice) : null;
  const detailSpecs = [
    { label: 'Категория', value: product.category?.name ?? 'Не указана' },
    { label: 'Артикул', value: selectedVariant?.sku ?? 'Выберите размер' },
    { label: 'Цвет', value: selectedVariant?.color ?? 'Не указан' },
    {
      label: 'Размер',
      value: selectedVariant ? displaySize(product.size_grid, selectedVariant.size, true) : 'Выберите размер',
    },
    { label: 'Остаток', value: selectedVariant ? `${selectedVariant.available_quantity} шт.` : '—' },
  ];

  return (
    <div className="page page--detail">
      <TopBar
        title="Товар"
        backFallback="/main"
        right={
          <button className={`icon-button favorite-button ${favorite ? 'is-active' : ''}`} type="button" disabled={favoriteBusy} onClick={() => void toggleFavorite()}>
            {favorite ? '♥' : '♡'}
          </button>
        }
      />

      {notice ? (
        <InlineNotice tone={notice.includes('добавлен') || notice.includes('модерации') ? 'success' : 'warning'}>
          <span>{notice}</span>
          <button type="button" onClick={() => setNotice(null)}>
            ×
          </button>
        </InlineNotice>
      ) : null}
      {quickCart.picker}

      <section className="product-gallery">
        <ProductImageCarousel product={product} variant="detail" />
      </section>

      <section className="detail-card">
        <div className="price-block">
          <div className="price-stack">
            <strong>{formatPrice(product.base_price)}</strong>
            {oldPrice ? (
              <span>
                <del>{formatPrice(oldPrice)}</del>
                {discount ? <em>{discount}</em> : null}
              </span>
            ) : null}
          </div>
          <span>{product.is_available ? 'В наличии' : 'Нет в наличии'}</span>
        </div>
        <h1>{product.name}</h1>
        {averageRating ? (
          <p className="rating-line">★ {averageRating.toFixed(1)} · {reviews.length} отзывов</p>
        ) : (
          <p className="rating-line">Отзывов пока нет</p>
        )}
      </section>

      <section className="detail-card product-fit-hint">
        <p>Мы подбираем размер по росту и весу.</p>
      </section>

      <section className="detail-card variant-selector-card">
        {showColorSelector ? (
          <>
            <div className="selector-heading">
              <h2>Цвет</h2>
              {selectedColorOption ? <span>{selectedColorOption.label}</span> : null}
            </div>
            <div className="variant-carousel color-carousel" aria-label="Доступные цвета">
              {colorOptions.map((option) => (
                <ColorButton
                  key={option.key}
                  option={option}
                  selected={selectedColorKey === option.key}
                  onSelect={() => selectColor(option.key)}
                />
              ))}
            </div>
          </>
        ) : null}

        <h2>{product.size_grid === 'shoes_eu' ? 'EU размер' : product.size_grid === 'shoes_ru' ? 'RU размер' : 'Размер'}</h2>
        {selectedColorVariants.length > 0 ? (
          <div className="variant-carousel" aria-label="Доступные размеры">
            {selectedColorVariants.map((variant) => (
              <VariantButton
                key={variant.id}
                selected={selectedVariantId === variant.id}
                sizeGrid={product.size_grid}
                variant={variant}
                onSelect={() => setSelectedVariantId(variant.id)}
              />
            ))}
          </div>
        ) : (
          <p className="muted-text">Доступных вариантов сейчас нет.</p>
        )}
      </section>

      {product.related_products && product.related_products.length > 0 ? (
        <section className="detail-card related-products-section">
          <h2>Похожие товары</h2>
          <div className="related-products-carousel">
            {product.related_products.map((relatedProduct) => (
              <ProductCard
                key={relatedProduct.id}
                product={relatedProduct}
                onAddToCart={quickCart.addToCart}
              />
            ))}
          </div>
        </section>
      ) : null}

      <section className="detail-card description-card">
        <h2>Описание</h2>
        <p className={`description-card__copy ${descriptionExpanded ? '' : 'is-collapsed'}`}>
          {product.description?.trim() || 'Описание скоро появится.'}
        </p>
        {descriptionExpanded ? (
          <dl className="spec-list description-card__specs">
            {detailSpecs.map((spec) => (
              <div key={spec.label}><dt>{spec.label}</dt><dd>{spec.value}</dd></div>
            ))}
          </dl>
        ) : null}
        <button
          className="description-card__toggle"
          type="button"
          aria-expanded={descriptionExpanded}
          onClick={() => setDescriptionExpanded((current) => !current)}
        >
          {descriptionExpanded ? 'Скрыть' : 'Ещё...'}
        </button>
      </section>

      <section className="detail-card">
        <h2>Отзывы</h2>
        {reviews.length === 0 ? (
          <EmptyState title="Отзывов пока нет" message="Первый отзыв появится после модерации." />
        ) : (
          <div className="review-list">
            {reviews.map((review) => (
              <article className="review-card" key={review.id}>
                <strong>{'★'.repeat(review.rating)}{'☆'.repeat(5 - review.rating)}</strong>
                <p>{review.text}</p>
                <span>{review.status === 'PENDING' ? 'На модерации' : formatDate(review.created_at)}</span>
              </article>
            ))}
          </div>
        )}

        <form className="review-form" onSubmit={submitReview}>
          <div className="review-rating-field">
            <span id="review-rating-label">Оценка</span>
            <div
              className="star-rating"
              role="radiogroup"
              aria-labelledby="review-rating-label"
              onKeyDown={handleReviewRatingKeyDown}
            >
              {[1, 2, 3, 4, 5].map((rating) => (
                <button
                  className={`star-rating__button ${rating <= reviewRating ? 'is-selected' : ''}`}
                  key={rating}
                  type="button"
                  role="radio"
                  aria-checked={reviewRating === rating}
                  aria-label={`${rating} из 5`}
                  disabled={reviewBusy}
                  onClick={() => changeReviewRating(rating)}
                >
                  <span aria-hidden="true">★</span>
                </button>
              ))}
            </div>
            <small>{reviewRating} из 5</small>
          </div>
          <label>
            Текст отзыва
            <textarea
              value={reviewText}
              onChange={(event) => setReviewText(event.target.value)}
              placeholder="Что понравилось?"
              rows={4}
            />
          </label>
          <button className="secondary-button" type="submit" disabled={reviewBusy || !reviewText.trim()}>
            Отправить отзыв
          </button>
        </form>
      </section>

      <div className="detail-cta">
        <span className="detail-cta__price">
          <strong>{formatPrice(product.base_price)}</strong>
          {oldPrice ? <del>{formatPrice(oldPrice)}</del> : null}
        </span>
        <div className="detail-cta__actions">
          <button
            className="secondary-button"
            type="button"
            disabled={purchaseActionsDisabled}
            onClick={() => void runCartAction('buy')}
          >
            {cartAction === 'buy' ? 'Открываем...' : 'Купить сейчас'}
          </button>
          <button
            className="primary-button"
            type="button"
            disabled={cartActionDisabled}
            onClick={() => void runCartAction('cart')}
          >
            {cartAction === 'cart' ? 'Добавляем...' : inCart ? 'Перейти в корзину' : 'В корзину'}
          </button>
        </div>
      </div>
    </div>
  );
}

async function getServerFavoriteState(productId: number) {
  try {
    const favorites = await getFavorites({ dedupe: false, retry: false, networkImpact: 'local' });
    return favorites.items.some((favorite) => favorite.product_id === productId);
  } catch {
    return null;
  }
}

function isFavoriteAlreadyExistsError(error: unknown) {
  const maybeError = error as { status?: number; message?: string; details?: unknown };
  if (maybeError?.status !== 409) {
    return false;
  }

  const detail = typeof maybeError.details === 'string'
    ? maybeError.details
    : maybeError.details && typeof maybeError.details === 'object'
      ? JSON.stringify(maybeError.details)
      : '';
  return `${maybeError.message ?? ''} ${detail}`.toLowerCase().includes('favorite');
}

function ColorButton({
  option,
  selected,
  onSelect,
}: {
  option: ColorOption;
  selected: boolean;
  onSelect: () => void;
}) {
  return (
    <button
      className={`color-button ${selected ? 'is-selected' : ''} ${option.availableCount <= 0 ? 'is-unavailable' : ''}`}
      type="button"
      onClick={onSelect}
    >
      <strong>{option.label}</strong>
      <span>{option.availableCount <= 0 ? 'нет' : `${option.availableCount} шт.`}</span>
    </button>
  );
}

function VariantButton({
  variant,
  sizeGrid,
  selected,
  onSelect,
}: {
  variant: ProductVariant;
  sizeGrid: Product['size_grid'];
  selected: boolean;
  onSelect: () => void;
}) {
  const disabled = variant.available_quantity <= 0;

  return (
    <button
      className={`variant-button ${selected ? 'is-selected' : ''}`}
      disabled={disabled}
      type="button"
      onClick={onSelect}
    >
      <strong>{displaySize(sizeGrid, variant.size)}</strong>
      <span>{disabled ? 'нет' : `${variant.available_quantity} шт.`}</span>
    </button>
  );
}
