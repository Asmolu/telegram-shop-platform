import React from 'react';
import type { Product } from '../api';
import { Link } from '../router/RouterProvider';
import { formatCompactPrice, formatDiscountPercent, getDisplayOldPrice } from '../utils/format';
import { getProductBadge } from '../utils/images';
import { displaySize, sortVariants } from '../utils/sizes';
import { CartIcon } from './Icons';
import { ProductImageCarousel } from './ProductImageCarousel';

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
  const sizes = sortVariants(product.variants, product.size_grid)
    .filter((variant) => variant.is_active && variant.available_quantity > 0)
    .map((variant) => variant.size)
    .filter((size, index, all) => all.indexOf(size) === index)
    .slice(0, 3);

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
      <Link className="product-card__media" to={`/product/${product.id}`}>
        <ProductImageCarousel product={product} variant="card" />
        {badge ? (
          <span
            className={`product-badge product-badge--${badgeType} product-badge--${badgePosition}`}
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
          {busyAction === 'favorite' ? '…' : favorite ? '♥' : '♡'}
        </button>
      ) : null}
      <div className={`product-card__body ${onAddToCart ? '' : 'product-card__body--no-action'}`}>
        <Link className="product-card__info" to={`/product/${product.id}`}>
          <span className="product-card__price-row">
            <strong className="product-card__price">{formatCompactPrice(product.base_price)}</strong>
            {oldPrice ? <del>{formatCompactPrice(oldPrice)}</del> : null}
          </span>
          <span className="product-card__title">{product.name}</span>
          <span className="product-card__meta">
            {product.is_available ? 'В наличии' : 'Нет в наличии'}
          </span>
          {sizes.length > 0 ? (
            <span className="size-row">
              {sizes.map((size) => (
                <span className="size-pill" key={size}>
                  {displaySize(product.size_grid, size)}
                </span>
              ))}
            </span>
          ) : null}
        </Link>
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
    </article>
  );
}
