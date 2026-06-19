import { getApiOrigin } from '../api';
import type {
  Product,
  ProductImageBadgeColor,
  ProductImageBadgePosition,
  ProductImageBadgeType,
} from '../api';

const BADGE_COLORS = new Set<ProductImageBadgeColor>([
  'purple',
  'pink',
  'red',
  'orange',
  'blue',
  'green',
  'black',
  'white',
]);
const BADGE_POSITIONS = new Set<ProductImageBadgePosition>([
  'top-left',
  'top-right',
  'bottom-left',
  'bottom-right',
]);

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
  return getProductImageItems(product)[0]?.url ?? null;
}

export function getProductImageItems(product: Product) {
  return [...product.images]
    .sort((left, right) => {
      if (left.is_primary !== right.is_primary) {
        return left.is_primary ? -1 : 1;
      }

      return left.position - right.position || left.id - right.id;
    })
    .map((image) => {
      const url = normalizeAssetUrl(image.url || image.file_path);

      return url
        ? {
            id: String(image.id),
            url,
            alt: image.alt_text ?? product.name,
          }
        : null;
    })
    .filter((image): image is { id: string; url: string; alt: string } => image !== null);
}

export function getProductBadge(product: Product) {
  const configuredBadge = getProductImageBadge(product);
  if (configuredBadge) {
    return configuredBadge;
  }

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

export function getProductImageBadge(product: Product) {
  if (product.image_badge_type === 'new') return 'NEW';
  if (product.image_badge_type === 'sale') return 'Распродажа';
  if (product.image_badge_type === 'hit') return 'Хит';
  if (product.image_badge_type === 'exclusive') return 'Эксклюзив';
  if (product.image_badge_type === 'custom') return product.image_badge_text?.trim() || null;
  return null;
}

export function getProductBadgeColor(
  product: Product,
  badgeType: ProductImageBadgeType = product.image_badge_type,
): ProductImageBadgeColor {
  if (product.image_badge_color && BADGE_COLORS.has(product.image_badge_color)) {
    return product.image_badge_color;
  }

  if (badgeType === 'sale') return 'red';
  if (badgeType === 'hit') return 'orange';
  return 'purple';
}

export function getProductBadgePosition(
  product: Product,
  badgeType: ProductImageBadgeType = product.image_badge_type,
): ProductImageBadgePosition {
  if (product.image_badge_position && BADGE_POSITIONS.has(product.image_badge_position)) {
    return product.image_badge_position;
  }

  return badgeType === 'new' ? 'top-left' : 'bottom-left';
}
