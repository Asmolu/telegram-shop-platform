import React from 'react';
import type { Product } from '../api';
import { Link } from '../router/RouterProvider';
import { formatDiscountPercent, formatPrice, getDisplayOldPrice } from '../utils/format';
import { getProductBadge } from '../utils/images';
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
  const oldPrice = getDisplayOldPrice(product.base_price, product.old_price, product.compare_at_price);
  const discount = oldPrice ? formatDiscountPercent(product.base_price, oldPrice) : null;
  const sizes = product.variants
    .filter((variant) => variant.is_active && variant.available_quantity > 0)
    .map((variant) => variant.size)
    .filter((size, index, all) => all.indexOf(size) === index)
    .slice(0, 4);

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
        {badge ? <span className={`product-badge product-badge--${badge.toLowerCase()}`}>{badge}</span> : null}
        {discount ? <span className="product-discount-badge">{discount}</span> : null}
      </Link>
      <button
        className={`icon-button favorite-button ${favorite ? 'is-active' : ''}`}
        type="button"
        aria-label={favorite ? 'Убрать из избранного' : 'Добавить в избранное'}
        disabled={busyAction !== null}
        onClick={() => void runAction('favorite', onFavoriteToggle)}
      >
        {busyAction === 'favorite' ? '…' : favorite ? '♥' : '♡'}
      </button>
      <Link className="product-card__body" to={`/product/${product.id}`}>
        <span className="product-card__price-row">
          <strong className="product-card__price">{formatPrice(product.base_price)}</strong>
          {oldPrice ? <del>{formatPrice(oldPrice)}</del> : null}
        </span>
        <span className="product-card__title">{product.name}</span>
        <span className="product-card__meta">
          {product.is_available ? 'В наличии' : 'Нет в наличии'}
        </span>
        {sizes.length > 0 ? (
          <span className="size-row">
            {sizes.map((size) => (
              <span className="size-pill" key={size}>
                {size}
              </span>
            ))}
          </span>
        ) : null}
      </Link>
      {onAddToCart ? (
        <div className="product-card__actions">
          <button
            className="add-cart-button"
            type="button"
            disabled={busyAction !== null || !product.is_available}
            onClick={() => void runAction('cart', onAddToCart)}
          >
            {busyAction === 'cart' ? '…' : 'В корзину'}
          </button>
        </div>
      ) : null}
    </article>
  );
}
