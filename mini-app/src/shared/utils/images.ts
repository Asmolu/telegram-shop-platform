import { getApiOrigin } from '../api';
import type {
  Product,
  ProductImage,
  ProductImageBadgeColor,
  ProductImageBadgePosition,
  ProductImageBadgeType,
} from '../api';

export type ProductImageVariant = 'thumbnail' | 'card' | 'detail' | 'original';

export type ProductImageItem = {
  id: string;
  url: string;
  alt: string;
  srcSet?: string;
  sizes?: string;
};

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

export function getProductImageUrl(product: Product, variant: ProductImageVariant = 'card') {
  return getProductImageItems(product, variant)[0]?.url ?? null;
}

export function getProductImageItems(
  product: Product,
  variant: ProductImageVariant = 'card',
): ProductImageItem[] {
  const galleryImages = product.images ?? [];
  if (galleryImages.length === 0) {
    return getCompactProductImageItem(product, variant);
  }

  return [...galleryImages]
    .sort((left, right) => {
      if (left.is_primary !== right.is_primary) {
        return left.is_primary ? -1 : 1;
      }

      return left.position - right.position || left.id - right.id;
    })
    .map<ProductImageItem | null>((image) => {
      const url = normalizeAssetUrl(getVariantPath(image, variant));

      return url
        ? {
            id: String(image.id),
            url,
            alt: image.alt_text ?? product.name,
            srcSet: getProductImageSrcSet(image, variant),
            sizes: getProductImageSizes(variant),
          }
        : null;
    })
    .filter((image): image is ProductImageItem => image !== null);
}

export function getProductImageSrcSet(
  image: ProductImage,
  variant: ProductImageVariant = 'card',
) {
  const widths = variant === 'detail'
    ? ([['thumbnail', 240], ['card', 480], ['detail', 1200]] as const)
    : variant === 'thumbnail'
      ? ([['thumbnail', 240], ['card', 480]] as const)
      : ([['thumbnail', 240], ['card', 480]] as const);
  const seen = new Set<string>();
  const entries = widths
    .map(([name, width]) => {
      const url = normalizeAssetUrl(getVariantPath(image, name));
      if (!url || seen.has(url)) {
        return null;
      }
      seen.add(url);
      return `${url} ${width}w`;
    })
    .filter((entry): entry is string => entry !== null);

  return entries.length > 1 ? entries.join(', ') : undefined;
}

export function getProductImageSizes(variant: ProductImageVariant = 'card') {
  if (variant === 'detail') {
    return '(max-width: 640px) 100vw, 640px';
  }
  if (variant === 'thumbnail') {
    return '96px';
  }
  return '(max-width: 480px) 50vw, 240px';
}

function getVariantPath(image: ProductImage, variant: ProductImageVariant) {
  const variants = image.image_variants ?? {};
  if (variant === 'thumbnail') {
    return (
      image.thumbnail_url
      ?? variants.thumbnail
      ?? uploadPathToUrl(image.thumbnail_path)
      ?? image.card_url
      ?? variants.card
      ?? image.url
      ?? image.image_url
      ?? uploadPathToUrl(image.file_path)
    );
  }
  if (variant === 'card') {
    return (
      image.card_url
      ?? variants.card
      ?? uploadPathToUrl(image.card_path)
      ?? image.thumbnail_url
      ?? variants.thumbnail
      ?? image.url
      ?? image.image_url
      ?? uploadPathToUrl(image.file_path)
    );
  }
  if (variant === 'detail') {
    return (
      image.detail_url
      ?? variants.detail
      ?? uploadPathToUrl(image.detail_path)
      ?? image.card_url
      ?? variants.card
      ?? image.url
      ?? image.image_url
      ?? uploadPathToUrl(image.file_path)
    );
  }
  return image.url ?? image.image_url ?? uploadPathToUrl(image.file_path);
}

function getCompactProductImageItem(
  product: Product,
  variant: ProductImageVariant,
): ProductImageItem[] {
  const preferredUrl = variant === 'thumbnail'
    ? product.thumbnail_image_url ?? product.image_url
    : product.image_url ?? product.thumbnail_image_url;
  const url = normalizeAssetUrl(preferredUrl);

  if (!url) {
    return [];
  }

  const thumbnailUrl = normalizeAssetUrl(product.thumbnail_image_url);
  const cardUrl = normalizeAssetUrl(product.image_url);
  const srcSet = compactSrcSet(thumbnailUrl, cardUrl);

  return [{
    id: `product-${product.id}`,
    url,
    alt: product.name,
    srcSet,
    sizes: getProductImageSizes(variant),
  }];
}

function compactSrcSet(thumbnailUrl: string | null, cardUrl: string | null) {
  const entries: string[] = [];
  if (thumbnailUrl) {
    entries.push(`${thumbnailUrl} 240w`);
  }
  if (cardUrl && cardUrl !== thumbnailUrl) {
    entries.push(`${cardUrl} 480w`);
  }
  return entries.length > 1 ? entries.join(', ') : undefined;
}

function uploadPathToUrl(path?: string | null) {
  if (!path) {
    return null;
  }
  if (/^https?:\/\//i.test(path) || path.startsWith('/')) {
    return path;
  }
  return `/uploads/${path}`;
}

export function getProductBadge(product: Product) {
  const configuredBadge = getProductImageBadge(product);
  if (configuredBadge) {
    return configuredBadge;
  }

  const tags = (product.tags ?? []).map((tag) => `${tag.slug} ${tag.name}`.toLowerCase());

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
