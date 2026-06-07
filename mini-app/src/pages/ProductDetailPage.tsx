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
import { useAuth } from '../shared/auth/AuthProvider';
import { getAuthPath, getNumericRouteParam, useRouter, withReturnTo } from '../shared/router/RouterProvider';
import { EmptyState, ErrorState, InlineNotice, PageLoader, ProductImageCarousel, TopBar } from '../shared/ui';
import { formatDate, formatPrice } from '../shared/utils/format';

export function ProductDetailPage() {
  const { currentPath, pathname, navigate } = useRouter();
  const { isAuthenticated } = useAuth();
  const productId = getNumericRouteParam(pathname, '/product/');
  const [product, setProduct] = React.useState<Product | null>(null);
  const [reviews, setReviews] = React.useState<Review[]>([]);
  const [cart, setCart] = React.useState<Cart | null>(null);
  const [favorite, setFavorite] = React.useState(false);
  const [selectedVariantId, setSelectedVariantId] = React.useState<number | null>(null);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);
  const [notice, setNotice] = React.useState<string | null>(null);
  const [reviewText, setReviewText] = React.useState('');
  const [reviewRating, setReviewRating] = React.useState(5);
  const [reviewBusy, setReviewBusy] = React.useState(false);

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
          setReviews(reviewsResult.items);
          setFavorite(favoritesResult.items.some((item) => item.product_id === productResult.id));
          setCart(cartResult);
          const activeVariant = productResult.variants.find((variant) => variant.is_active && variant.available_quantity > 0);
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

  const selectedVariant = product?.variants.find((variant) => variant.id === selectedVariantId) ?? null;
  const inCart = Boolean(
    selectedVariant && cart?.items.some((item) => item.product_variant.id === selectedVariant.id),
  );
  const averageRating = reviews.length
    ? reviews.reduce((sum, review) => sum + review.rating, 0) / reviews.length
    : null;

  async function toggleFavorite() {
    if (!product) return;
    if (!isAuthenticated) {
      navigate(getAuthPath(currentPath));
      return;
    }

    try {
      if (favorite) {
        await removeFavorite(product.id);
        setFavorite(false);
      } else {
        await addFavorite(product.id);
        setFavorite(true);
      }
    } catch (actionError) {
      setNotice(toApiErrorMessage(actionError));
    }
  }

  async function addSelectedToCart() {
    if (!product || !selectedVariant) {
      setNotice('Выберите доступный размер.');
      return;
    }
    if (!isAuthenticated) {
      navigate(getAuthPath(currentPath));
      return;
    }
    if (inCart) {
      navigate(withReturnTo('/cart?tab=cart', currentPath));
      return;
    }

    try {
      const nextCart = await addCartItem(product.id, selectedVariant.id, 1);
      setCart(nextCart);
      window.dispatchEvent(new Event('miniapp:cart-updated'));
      setNotice('Товар добавлен в корзину.');
    } catch (actionError) {
      setNotice(toApiErrorMessage(actionError));
    }
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

  if (loading) {
    return (
      <div className="page">
        <TopBar title="Товар" onBack={() => navigate('/main')} />
        <PageLoader text="Загружаем товар..." />
      </div>
    );
  }

  if (error || !product) {
    return (
      <div className="page">
        <TopBar title="Товар" onBack={() => navigate('/main')} />
        <ErrorState message={error ?? 'Товар не найден'} actionLabel="К ленте" onAction={() => navigate('/main')} />
      </div>
    );
  }

  const activeVariants = product.variants.filter((variant) => variant.is_active);

  return (
    <div className="page page--detail">
      <TopBar
        title="Товар"
        onBack={() => window.history.length > 1 ? window.history.back() : navigate('/main')}
        right={
          <button className={`icon-button favorite-button ${favorite ? 'is-active' : ''}`} type="button" onClick={() => void toggleFavorite()}>
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

      <section className="product-gallery">
        <ProductImageCarousel product={product} variant="detail" />
      </section>

      <section className="detail-card">
        <div className="price-block">
          <strong>{formatPrice(product.base_price)}</strong>
          <span>{product.is_available ? 'В наличии' : 'Нет в наличии'}</span>
        </div>
        <h1>{product.name}</h1>
        {averageRating ? (
          <p className="rating-line">★ {averageRating.toFixed(1)} · {reviews.length} отзывов</p>
        ) : (
          <p className="rating-line">Отзывов пока нет</p>
        )}
      </section>

      <section className="detail-card">
        <h2>Размер</h2>
        {activeVariants.length > 0 ? (
          <div className="variant-grid">
            {activeVariants.map((variant) => (
              <VariantButton
                key={variant.id}
                selected={selectedVariantId === variant.id}
                variant={variant}
                onSelect={() => setSelectedVariantId(variant.id)}
              />
            ))}
          </div>
        ) : (
          <p className="muted-text">Доступных вариантов сейчас нет.</p>
        )}
      </section>

      {product.description ? (
        <section className="detail-card">
          <h2>Описание</h2>
          <p>{product.description}</p>
        </section>
      ) : null}

      <section className="detail-card">
        <h2>Характеристики</h2>
        <dl className="spec-list">
          <div><dt>Категория</dt><dd>{product.category?.name ?? 'Не указана'}</dd></div>
          <div><dt>Артикул</dt><dd>{selectedVariant?.sku ?? 'Выберите размер'}</dd></div>
          <div><dt>Цвет</dt><dd>{selectedVariant?.color ?? 'Не указан'}</dd></div>
          <div><dt>Остаток</dt><dd>{selectedVariant ? `${selectedVariant.available_quantity} шт.` : '—'}</dd></div>
        </dl>
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
          <label>
            Оценка
            <select value={reviewRating} onChange={(event) => setReviewRating(Number(event.target.value))}>
              {[5, 4, 3, 2, 1].map((rating) => (
                <option value={rating} key={rating}>{rating}</option>
              ))}
            </select>
          </label>
          <label>
            Текст отзыва
            <textarea
              value={reviewText}
              onChange={(event) => setReviewText(event.target.value)}
              placeholder="Что понравилось?"
              rows={3}
            />
          </label>
          <button className="secondary-button" type="submit" disabled={reviewBusy || !reviewText.trim()}>
            Отправить отзыв
          </button>
        </form>
      </section>

      <div className="detail-cta">
        <strong>{formatPrice(product.base_price)}</strong>
        <button className="primary-button" type="button" onClick={() => void addSelectedToCart()}>
          {inCart ? 'Перейти в корзину' : 'В корзину'}
        </button>
      </div>
    </div>
  );
}

function VariantButton({
  variant,
  selected,
  onSelect,
}: {
  variant: ProductVariant;
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
      <strong>{variant.size}</strong>
      <span>{disabled ? 'нет' : `${variant.available_quantity} шт.`}</span>
    </button>
  );
}
