import React from 'react';
import type { Product } from '../api';
import { Link } from '../router/RouterProvider';
import { formatCompactPrice, formatDiscountPercent, getDisplayOldPrice } from '../utils/format';
import { getProductBadge } from '../utils/images';
import { CartIcon, HeartIcon } from './Icons';
import { ProductImageCarousel } from './ProductImageCarousel';

function toFiniteNumber(value: string | number | null | undefined) {
  if (value === null || value === undefined || value === '') {
    return null;
  }

  const numberValue = Number(value);
  return Number.isFinite(numberValue) ? numberValue : null;
}

function formatRating(value: number) {
  return value.toLocaleString('ru-RU', {
    maximumFractionDigits: 1,
    minimumFractionDigits: Number.isInteger(value) ? 0 : 1,
  });
}

function formatReviewCount(count: number) {
  const normalized = Math.max(Math.trunc(count), 0);
  const mod10 = normalized % 10;
  const mod100 = normalized % 100;
  const noun = mod10 === 1 && mod100 !== 11
    ? 'отзыв'
    : mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)
      ? 'отзыва'
      : 'отзывов';

  return `${normalized} ${noun}`;
}

function getReviewLine(product: Product) {
  const rating = [
    product.average_rating,
    product.rating,
  ].map(toFiniteNumber).find((value): value is number => value !== null && value > 0);
  const reviewCount = [
    product.reviews_count,
    product.review_count,
    product.rating_count,
  ].map(toFiniteNumber).find((value): value is number => value !== null && value > 0);

  if (rating && reviewCount) {
    return `★ ${formatRating(rating)} · ${formatReviewCount(reviewCount)}`;
  }

  if (rating) {
    return `★ ${formatRating(rating)}`;
  }

  if (reviewCount) {
    return formatReviewCount(reviewCount);
  }

  return 'Пока нет отзывов';
}

export function ProductCard({
  product,
  favorite = false,
  onFavoriteToggle,
  onAddToCart,
}: {
  product: Product;
  favorite?: boolean;
  onFavoriteToggle?: (product: Product) => void | Promise<void>;
  onAddToCart?: (product: Product) => void | Promise<void>;
}) {
  const [busyAction, setBusyAction] = React.useState<'favorite' | 'cart' | null>(null);
  const badge = getProductBadge(product);
  const badgeType = product.image_badge_type !== 'none'
    ? product.image_badge_type
    : badge?.toLowerCase() === 'new'
      ? 'new'
      : badge?.toLowerCase() === 'sale'
        ? 'sale'
        : 'custom';
  const badgePosition = badgeType === 'new' ? 'top' : 'bottom';
  const oldPrice = getDisplayOldPrice(product.base_price, product.old_price, product.compare_at_price);
  const discount = oldPrice ? formatDiscountPercent(product.base_price, oldPrice) : null;
  const brand = product.brand?.trim() || 'Без бренда';
  const reviewLine = getReviewLine(product);

  async function runAction(action: 'favorite' | 'cart', callback?: (product: Product) => void | Promise<void>) {
    if (!callback) {
      return;
    }

    setBusyAction(action);
    try {
      await callback(product);
    } finally {
      setBusyAction(null);
    }
  }

  return (
    <article className="product-card">
      <div className="product-card__media-shell">
        <Link className="product-card__media" to={`/product/${product.id}`}>
          <ProductImageCarousel product={product} variant="card" />
          {badge ? (
            <span
              className={`product-badge product-badge--${badgeType} product-badge--${badgePosition} ${
                discount && badgePosition === 'bottom' ? 'product-badge--above-discount' : ''
              }`}
            >
              {badge}
            </span>
          ) : null}
          {discount ? <span className="product-discount-badge">{discount}</span> : null}
        </Link>
        {onFavoriteToggle ? (
          <button
            className={`icon-button favorite-button ${favorite ? 'is-active' : ''}`}
            type="button"
            aria-label={favorite ? 'Убрать из избранного' : 'Добавить в избранное'}
            disabled={busyAction !== null}
            onClick={() => void runAction('favorite', onFavoriteToggle)}
          >
            {busyAction === 'favorite' ? (
              <span aria-hidden="true">...</span>
            ) : (
              <HeartIcon filled={favorite} />
            )}
          </button>
        ) : null}
        {onAddToCart ? (
          <button
            className="product-card__cart-button"
            type="button"
            aria-label="Добавить в корзину"
            disabled={busyAction !== null || !product.is_available}
            onClick={() => void runAction('cart', onAddToCart)}
          >
            {busyAction === 'cart' ? <span aria-hidden="true">…</span> : <CartIcon />}
          </button>
        ) : null}
      </div>
      <div className={`product-card__body ${onAddToCart ? '' : 'product-card__body--no-action'}`}>
        <Link className="product-card__info" to={`/product/${product.id}`}>
          <span className="product-card__price-row">
            <strong className="product-card__price">{formatCompactPrice(product.base_price)}</strong>
            {oldPrice ? <del>{formatCompactPrice(oldPrice)}</del> : null}
          </span>
          <span className="product-card__brand">{brand}</span>
          <span className="product-card__title">{product.name}</span>
          <span className="product-card__review-line">{reviewLine}</span>
        </Link>
      </div>
    </article>
  );
}
