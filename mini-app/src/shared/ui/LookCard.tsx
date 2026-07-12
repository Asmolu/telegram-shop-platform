import React from 'react';
import type { LookCard as LookCardType } from '../api';
import { Link, useRouter, withReturnTo } from '../router/RouterProvider';
import { runLockedAction } from '../utils/actionLock';
import { formatCompactPrice, formatDiscountPercent, getDiscountBadgeTier, getDiscountPercent, getDisplayOldPrice, pluralizeProducts } from '../utils/format';
import { normalizeAssetUrl } from '../utils/images';
import { CartIcon } from './Icons';

export function LookCard({
  look,
  imageLoading = 'lazy',
  imageFetchPriority,
  onAddToCart,
}: {
  look: LookCardType;
  imageLoading?: 'eager' | 'lazy';
  imageFetchPriority?: 'high' | 'low' | 'auto';
  onAddToCart?: (look: LookCardType) => void | Promise<void>;
}) {
  const { currentPath } = useRouter();
  const [busy, setBusy] = React.useState(false);
  const actionLock = React.useRef({ current: false });
  const imageUrl = normalizeAssetUrl(look.primary_image_url);
  const lookPath = withReturnTo(`/looks/${encodeURIComponent(look.slug)}`, currentPath);
  const badgeType = look.image_badge_type ?? 'none';
  const badge = badgeType === 'new' ? 'NEW' : badgeType === 'sale' ? 'Распродажа' : badgeType === 'hit' ? 'Хит' : badgeType === 'exclusive' ? 'Эксклюзив' : badgeType === 'custom' ? look.image_badge_text?.trim() || null : null;
  const badgeColor = look.image_badge_color ?? (badgeType === 'sale' ? 'red' : badgeType === 'hit' ? 'orange' : 'purple');
  const badgePosition = look.image_badge_position ?? (badgeType === 'new' ? 'top-left' : 'bottom-left');
  const oldPrice = getDisplayOldPrice(look.price, look.old_price);
  const discountPercent = oldPrice ? getDiscountPercent(look.price, oldPrice) : null;
  const discount = oldPrice ? formatDiscountPercent(look.price, oldPrice) : null;
  const discountTier = getDiscountBadgeTier(discountPercent);

  async function addToCart() {
    if (!onAddToCart) {
      return;
    }
    await runLockedAction(actionLock.current, async () => {
      setBusy(true);
      try {
        await onAddToCart(look);
      } finally {
        setBusy(false);
      }
    });
  }

  return (
    <article className={`product-card look-card ${look.is_available ? '' : 'look-card--unavailable'}`}>
      <div className="product-card__media-shell look-card__media-shell">
        <Link className="product-card__media look-card__media" to={lookPath}>
        {imageUrl ? (
          <img
            src={imageUrl}
            alt={look.title}
            width={480}
            height={600}
            loading={imageLoading}
            fetchPriority={imageFetchPriority}
            decoding="async"
          />
        ) : (
          <span className="image-fallback look-card__fallback">
            <span>{look.title.slice(0, 1).toUpperCase()}</span>
          </span>
        )}
        {badge ? (
          <span className={`product-badge product-badge--${badgeType} product-badge--color-${badgeColor} product-badge--position-${badgePosition} product-badge--configured ${discountTier && badgePosition === 'bottom-left' ? `product-badge--above-discount product-badge--above-discount-tier-${discountTier}` : ''}`}>
            {badge}
          </span>
        ) : null}
        {discount && discountTier ? <span className={`product-discount-badge discount-badge--tier-${discountTier}`}>{discount}</span> : null}
        {!look.is_available ? <span className="look-card__availability">Недоступен</span> : null}
        </Link>
        {onAddToCart ? (
          <button
            className="product-card__cart-button"
            type="button"
            aria-label="Добавить образ в корзину"
            disabled={busy || !look.is_available}
            onClick={() => void addToCart()}
          >
            {busy ? <span aria-hidden="true">…</span> : <CartIcon />}
          </button>
        ) : null}
      </div>
      <div className={`product-card__body ${onAddToCart ? '' : 'product-card__body--no-action'} look-card__body`}>
        <Link className="product-card__info" to={lookPath}>
          <span className="product-card__brand">{pluralizeProducts(look.item_count)}</span>
          <span className="product-card__title">{look.title}</span>
          <span className="product-card__price-row">
            <strong className="product-card__price">{formatCompactPrice(look.price)}</strong>
            {oldPrice ? <del>{formatCompactPrice(oldPrice)}</del> : null}
          </span>
        </Link>
      </div>
    </article>
  );
}
