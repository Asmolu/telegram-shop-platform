import { getApiOrigin } from '../api';
import type { Product } from '../api';

export function normalizeAssetUrl(url?: string | null) {
  if (!url) {
    return null;
  }

  if (/^https?:\/\//i.test(url)) {
    return url;
  }

  const origin = getApiOrigin();
  if (!origin) {
    return url;
  }

  return `${origin}${url.startsWith('/') ? url : `/${url}`}`;
}

export function getProductImageUrl(product: Product) {
  const primary = product.images.find((image) => image.is_primary) ?? product.images[0];
  return normalizeAssetUrl(primary?.url ?? primary?.file_path);
}

export function getProductBadge(product: Product) {
  const tags = product.tags.map((tag) => `${tag.slug} ${tag.name}`.toLowerCase());

  if (tags.some((tag) => tag.includes('sale') || tag.includes('скид'))) {
    return 'SALE';
  }

  if (tags.some((tag) => tag.includes('new') || tag.includes('нов'))) {
    return 'NEW';
  }

  if (new Date(product.created_at).getTime() > Date.now() - 1000 * 60 * 60 * 24 * 21) {
    return 'NEW';
  }

  return null;
}
