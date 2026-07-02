import React from 'react';
import type { LookCard as LookCardType } from '../api';
import { Link, useRouter, withReturnTo } from '../router/RouterProvider';
import { formatCompactPrice, pluralizeProducts } from '../utils/format';
import { normalizeAssetUrl } from '../utils/images';

export function LookCard({
  look,
  imageLoading = 'lazy',
  imageFetchPriority,
}: {
  look: LookCardType;
  imageLoading?: 'eager' | 'lazy';
  imageFetchPriority?: 'high' | 'low' | 'auto';
}) {
  const { currentPath } = useRouter();
  const imageUrl = normalizeAssetUrl(look.primary_image_url);
  const lookPath = withReturnTo(`/looks/${encodeURIComponent(look.slug)}`, currentPath);

  return (
    <article className={`product-card look-card ${look.is_available ? '' : 'look-card--unavailable'}`}>
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
        <span className="look-card__badge">Образ</span>
        {!look.is_available ? <span className="look-card__availability">Недоступен</span> : null}
      </Link>
      <div className="product-card__body product-card__body--no-action look-card__body">
        <Link className="product-card__info" to={lookPath}>
          <span className="product-card__brand">{pluralizeProducts(look.item_count)}</span>
          <span className="product-card__title">{look.title}</span>
          <span className="product-card__review-line">
            {look.available_sizes.length > 0 ? look.available_sizes.join(' / ') : 'Нет общего размера'}
          </span>
          <span className="product-card__price-row">
            <strong className="product-card__price">{formatCompactPrice(look.price)}</strong>
            {look.old_price ? <del>{formatCompactPrice(look.old_price)}</del> : null}
          </span>
        </Link>
      </div>
    </article>
  );
}
