import { describe, expect, it } from 'vitest';
import { getLogicalBackPath, isFirstLevelRoutePath } from './RouterProvider';

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
    ['/category/7', '/categories'],
    ['/search/results?q=hoodie', '/search'],
    ['/search/results?tag_id=4&from=categories', '/categories'],
    ['/checkout?returnTo=%2Fproduct%2F10', '/cart?tab=cart'],
    ['/payment/42', '/cart?tab=orders'],
    ['/order-success/42', '/cart?tab=orders'],
    ['/profile/personal-data', '/profile'],
  ])('returns the explicit logical parent for %s', (path, parent) => {
    expect(getLogicalBackPath(path)).toBe(parent);
  });

  it('uses a safe returnTo for product detail pages', () => {
    expect(getLogicalBackPath('/product/10?returnTo=%2Fsearch%2Fresults%3Fq%3Dhoodie')).toBe(
      '/search/results?q=hoodie',
    );
  });
});
