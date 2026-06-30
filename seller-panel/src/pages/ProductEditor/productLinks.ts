import type { Product, ProductVariant } from '../../shared/api';

export const MINI_APP_PRODUCT_LINK_BASE_URL = 'https://mini.stylexac.ru';

export type ProductLinkCategory = {
  id: number;
  name: string;
  slug: string;
};

export type ProductLinkGeneratorState =
  | 'save_first'
  | 'needs_category'
  | 'needs_variant'
  | 'ready';

export function getLinkableProductCategories(product: Product | null): ProductLinkCategory[] {
  if (!product) {
    return [];
  }

  const categories = new Map<number, ProductLinkCategory>();
  product.categories
    .slice()
    .sort((left, right) => left.priority - right.priority)
    .forEach((assignment) => {
      const category = assignment.category;
      if (category?.slug) {
        categories.set(category.id, {
          id: category.id,
          name: category.name,
          slug: category.slug,
        });
      }
    });

  if (categories.size === 0 && product.category?.slug) {
    categories.set(product.category.id, {
      id: product.category.id,
      name: product.category.name,
      slug: product.category.slug,
    });
  }

  return Array.from(categories.values());
}

export function getLinkableProductVariants(product: Product | null): ProductVariant[] {
  if (!product) {
    return [];
  }

  return product.variants.filter((variant) => variant.sku.trim().length > 0);
}

export function getProductLinkGeneratorState(
  product: Product | null,
  categories = getLinkableProductCategories(product),
  variants = getLinkableProductVariants(product),
): ProductLinkGeneratorState {
  if (!product?.id || !product.slug) {
    return 'save_first';
  }
  if (categories.length === 0) {
    return 'needs_category';
  }
  if (variants.length === 0) {
    return 'needs_variant';
  }
  return 'ready';
}

export function buildProductCustomerLink({
  categorySlug,
  productSlug,
  sku,
  baseUrl = MINI_APP_PRODUCT_LINK_BASE_URL,
}: {
  categorySlug: string;
  productSlug: string;
  sku: string;
  baseUrl?: string;
}) {
  const normalizedBaseUrl = baseUrl.replace(/\/+$/, '');
  return [
    `${normalizedBaseUrl}/category/${encodeURIComponent(categorySlug)}`,
    `/product/${encodeURIComponent(productSlug)}`,
    `?sku=${encodeURIComponent(sku)}`,
  ].join('');
}

export async function copyTextToClipboard(
  text: string,
  clipboard: Pick<Clipboard, 'writeText'> | undefined = globalThis.navigator?.clipboard,
) {
  if (!clipboard?.writeText) {
    return false;
  }

  await clipboard.writeText(text);
  return true;
}
