import type { ProductSizeGrid, ProductVariant } from '../api';

export const CLOTHING_SIZES = ['XS', 'S', 'M', 'L', 'XL', 'XXL', '3XL', 'ONE_SIZE'] as const;
export const SHOE_SIZES_EU = ['35', '36', '37', '38', '39', '40', '41', '42', '43', '44', '45', '46'] as const;
export const SHOE_SIZES_RU = SHOE_SIZES_EU;

export function sizesForGrid(sizeGrid: ProductSizeGrid): readonly string[] {
  return sizeGrid === 'shoes_eu' || sizeGrid === 'shoes_ru' ? SHOE_SIZES_EU : CLOTHING_SIZES;
}

export function displaySize(sizeGrid: ProductSizeGrid, size: string, detached = false): string {
  if (sizeGrid === 'shoes_eu') {
    return detached ? `EU ${size}` : size;
  }
  if (sizeGrid === 'shoes_ru') {
    return detached ? `RU ${size}` : size;
  }
  return size === 'ONE_SIZE' ? 'Единый размер' : size;
}

export function sortVariants(
  variants: ProductVariant[],
  sizeGrid: ProductSizeGrid,
): ProductVariant[] {
  const order = sizesForGrid(sizeGrid);
  return [...variants].sort((left, right) => {
    const leftIndex = order.indexOf(left.size);
    const rightIndex = order.indexOf(right.size);
    const normalizedLeft = leftIndex < 0 ? order.length : leftIndex;
    const normalizedRight = rightIndex < 0 ? order.length : rightIndex;
    return normalizedLeft - normalizedRight || left.color?.localeCompare(right.color ?? '') || left.id - right.id;
  });
}
