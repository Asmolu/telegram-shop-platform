import { describe, expect, it } from 'vitest';

import { getCategoryPageRoute } from './CategoryPage';

describe('getCategoryPageRoute', () => {
  it('keeps numeric category routes as id routes', () => {
    expect(getCategoryPageRoute('/category/7')).toEqual({
      mode: 'id',
      categoryId: 7,
      fallbackSlug: '7',
    });
  });

  it('supports category slug routes', () => {
    expect(getCategoryPageRoute('/category/futbolki')).toEqual({
      mode: 'slug',
      categorySlug: 'futbolki',
    });
  });
});
