import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

import { applyGeneratedProductSlug } from '../src/pages/ProductEditor/productSlugAutofill.ts';

const apiSource = readFileSync(new URL('../src/shared/api/client.ts', import.meta.url), 'utf8');
const pageSource = readFileSync(
  new URL('../src/pages/ProductEditor/ProductEditorPage.tsx', import.meta.url),
  'utf8',
);
const productListSource = readFileSync(
  new URL('../src/pages/Products/ProductsPage.tsx', import.meta.url),
  'utf8',
);
const i18nSource = readFileSync(new URL('../src/shared/i18n/index.tsx', import.meta.url), 'utf8');
const typesSource = readFileSync(new URL('../src/shared/api/types.ts', import.meta.url), 'utf8');

test('new product editor can apply a generated numeric product slug', () => {
  assert.equal(
    applyGeneratedProductSlug({
      mode: 'create',
      currentSlug: '',
      generatedSlug: '00001',
      wasManuallyEdited: false,
    }),
    '00001',
  );
});

test('manual slug edits are not overwritten by async generation', () => {
  assert.equal(
    applyGeneratedProductSlug({
      mode: 'create',
      currentSlug: '',
      generatedSlug: '00002',
      wasManuallyEdited: true,
    }),
    '',
  );
  assert.equal(
    applyGeneratedProductSlug({
      mode: 'create',
      currentSlug: 'manual-slug',
      generatedSlug: '00002',
      wasManuallyEdited: false,
    }),
    'manual-slug',
  );
});

test('editing an existing product does not apply generated product slugs', () => {
  assert.equal(
    applyGeneratedProductSlug({
      mode: 'edit',
      currentSlug: 'legacy-slug',
      generatedSlug: '00003',
      wasManuallyEdited: false,
    }),
    'legacy-slug',
  );
});

test('product editor requests and fills backend generated slugs only for new products', () => {
  assert.match(apiSource, /generateProductSlugs/);
  assert.match(apiSource, /\/products\/admin\/slugs\/next/);
  assert.match(pageSource, /api\.products\.generateProductSlugs\(1\)/);
  assert.match(pageSource, /if \(mode !== 'create'\)/);
  assert.match(pageSource, /slug: applyGeneratedProductSlug/);
});

test('save uses generated slug and blank create slug remains backend-generatable', () => {
  assert.match(pageSource, /const trimmedSlug = form\.slug\.trim\(\)/);
  assert.ok(pageSource.includes('...(trimmedSlug ? { slug: trimmedSlug } : {})'));
  assert.doesNotMatch(pageSource, /slugify\(event\.target\.value\)/);
});

test('product editor exposes visibility and returnability controls with checked defaults', () => {
  assert.match(pageSource, /isListed: true/);
  assert.match(pageSource, /isReturnable: true/);
  assert.match(pageSource, /loadedProduct\.is_listed \?\? true/);
  assert.match(pageSource, /loadedProduct\.is_returnable \?\? true/);
  assert.match(pageSource, /is_listed: form\.isListed/);
  assert.match(pageSource, /is_returnable: form\.isReturnable/);
  assert.match(pageSource, /productEditor\.isListed/);
  assert.match(pageSource, /productEditor\.isReturnable/);
  assert.match(i18nSource, /'productEditor\.isListed': 'Показывать в витрине'/);
  assert.match(i18nSource, /'productEditor\.isReturnable': 'Возвратный товар'/);
});

test('product list renders hidden and non-returnable badges', () => {
  assert.match(productListSource, /!product\.is_listed/);
  assert.match(productListSource, /!product\.is_returnable/);
  assert.match(productListSource, /products\.hiddenBadge/);
  assert.match(productListSource, /products\.nonReturnableBadge/);
  assert.match(i18nSource, /'products\.hiddenBadge': 'Скрыт'/);
  assert.match(i18nSource, /'products\.nonReturnableBadge': 'Невозвратный'/);
});

test('seller API types include product visibility and returnability fields', () => {
  assert.match(typesSource, /is_listed: boolean/);
  assert.match(typesSource, /is_returnable: boolean/);
  assert.match(typesSource, /is_listed\?: boolean/);
  assert.match(typesSource, /is_returnable\?: boolean/);
});
