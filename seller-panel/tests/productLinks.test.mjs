import assert from 'node:assert/strict';
import test from 'node:test';

import {
  buildProductCustomerLink,
  copyTextToClipboard,
  getLinkableProductCategories,
  getLinkableProductVariants,
  getProductLinkGeneratorState,
} from '../src/pages/ProductEditor/productLinks.ts';

function product(overrides = {}) {
  return {
    id: 10,
    name: 'Line Break Hoodie',
    slug: 'line-break-hoodie',
    category: null,
    categories: [
      {
        category_id: 2,
        priority: 2,
        category: { id: 2, name: 'Лето', slug: 'leto' },
      },
      {
        category_id: 1,
        priority: 1,
        category: { id: 1, name: 'Футболки', slug: 'futbolki' },
      },
    ],
    variants: [
      {
        id: 100,
        product_id: 10,
        size: 'M',
        color: 'Белый',
        sku: '00001',
        stock_quantity: 4,
        reserved_quantity: 0,
        available_quantity: 4,
        is_active: true,
        created_at: '2026-06-30T00:00:00Z',
        updated_at: '2026-06-30T00:00:00Z',
      },
      {
        id: 101,
        product_id: 10,
        size: 'L',
        color: 'Черный',
        sku: '00002',
        stock_quantity: 0,
        reserved_quantity: 0,
        available_quantity: 0,
        is_active: true,
        created_at: '2026-06-30T00:00:00Z',
        updated_at: '2026-06-30T00:00:00Z',
      },
    ],
    ...overrides,
  };
}

test('generated customer link includes category slug, product slug, and SKU', () => {
  assert.equal(
    buildProductCustomerLink({
      categorySlug: 'futbolki',
      productSlug: 'line-break-hoodie',
      sku: '00001',
    }),
    'https://mini.stylexac.ru/category/futbolki/product/line-break-hoodie?sku=00001',
  );
});

test('generated customer link supports numeric product slugs', () => {
  assert.equal(
    buildProductCustomerLink({
      categorySlug: 'futbolki',
      productSlug: '00042',
      sku: '00001',
    }),
    'https://mini.stylexac.ru/category/futbolki/product/00042?sku=00001',
  );
});

test('category and variant selects stay compact instead of rendering every combination', () => {
  const linkCategories = getLinkableProductCategories(product());
  const linkVariants = getLinkableProductVariants(product({
    variants: Array.from({ length: 50 }, (_, index) => ({
      ...product().variants[0],
      id: index + 1,
      sku: String(index + 1).padStart(5, '0'),
    })),
  }));

  assert.deepEqual(linkCategories.map((category) => category.slug), ['futbolki', 'leto']);
  assert.equal(linkVariants.length, 50);
});

test('generator state reports why a full customer link is unavailable', () => {
  assert.equal(getProductLinkGeneratorState(null), 'save_first');
  assert.equal(
    getProductLinkGeneratorState(product({ id: 0 })),
    'save_first',
  );
  assert.equal(
    getProductLinkGeneratorState(product({ categories: [], category: null })),
    'needs_category',
  );
  assert.equal(
    getProductLinkGeneratorState(product({ variants: [] })),
    'needs_variant',
  );
  assert.equal(getProductLinkGeneratorState(product()), 'ready');
});

test('category selection changes the generated customer URL', () => {
  const [primary, secondary] = getLinkableProductCategories(product());
  const [variant] = getLinkableProductVariants(product());

  assert.equal(
    buildProductCustomerLink({
      categorySlug: primary.slug,
      productSlug: 'line-break-hoodie',
      sku: variant.sku,
    }),
    'https://mini.stylexac.ru/category/futbolki/product/line-break-hoodie?sku=00001',
  );
  assert.equal(
    buildProductCustomerLink({
      categorySlug: secondary.slug,
      productSlug: 'line-break-hoodie',
      sku: variant.sku,
    }),
    'https://mini.stylexac.ru/category/leto/product/line-break-hoodie?sku=00001',
  );
});

test('variant selection changes the generated customer URL', () => {
  const [category] = getLinkableProductCategories(product());
  const [, variant] = getLinkableProductVariants(product());

  assert.equal(
    buildProductCustomerLink({
      categorySlug: category.slug,
      productSlug: 'line-break-hoodie',
      sku: variant.sku,
    }),
    'https://mini.stylexac.ru/category/futbolki/product/line-break-hoodie?sku=00002',
  );
});

test('clipboard helper reports success and unavailable clipboard fallback', async () => {
  const calls = [];
  const copied = await copyTextToClipboard('https://mini.stylexac.ru/link', {
    writeText: async (value) => calls.push(value),
  });
  const unavailable = await copyTextToClipboard('https://mini.stylexac.ru/link', undefined);

  assert.equal(copied, true);
  assert.deepEqual(calls, ['https://mini.stylexac.ru/link']);
  assert.equal(unavailable, false);
});
