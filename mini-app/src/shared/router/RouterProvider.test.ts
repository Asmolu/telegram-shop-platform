import { describe, expect, it } from 'vitest';
import {
  getCategoryProductRouteParams,
  getLogicalBackPath,
  getRouteId,
  isFirstLevelRoutePath,
} from './RouterProvider';

describe('logical mini app back routes', () => {
  it.each([
    '/',
    '/main',
    '/categories',
    '/search',
    '/cart?tab=cart',
    '/cart?tab=orders',
    '/profile',
  ])('treats %s as a first-level route', (path) => {
    expect(isFirstLevelRoutePath(path)).toBe(true);
    expect(getLogicalBackPath(path)).toBeNull();
  });

  it.each([
    ['/category/futbolki/product/line-break-hoodie?sku=00001', '/category/futbolki'],
    ['/category/7', '/categories'],
    ['/search/results?q=hoodie', '/search'],
    ['/search/results?tag_id=4&from=categories', '/categories'],
    ['/checkout?returnTo=%2Fproduct%2F10', '/cart?tab=cart'],
    ['/payment/42', '/cart?tab=orders'],
    ['/order-success/42', '/cart?tab=orders'],
    ['/orders/42/return', '/order-success/42'],
    ['/profile/personal-data', '/profile'],
  ])('returns the explicit logical parent for %s', (path, parent) => {
    expect(getLogicalBackPath(path)).toBe(parent);
  });

  it('uses a safe returnTo for product detail pages', () => {
    expect(getLogicalBackPath('/product/10?returnTo=%2Fsearch%2Fresults%3Fq%3Dhoodie')).toBe(
      '/search/results?q=hoodie',
    );
  });

  it('matches category-product links before generic category routes', () => {
    const pathname = '/category/futbolki/product/line-break-hoodie';

    expect(getCategoryProductRouteParams(pathname)).toEqual({
      categorySlug: 'futbolki',
      productSlug: 'line-break-hoodie',
    });
    expect(getRouteId(pathname)).toBe('product-detail');
  });

  it('resolves return request route ids', () => {
    expect(getRouteId('/orders/42/return')).toBe('return-request');
  });
});
