import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

import { applyGeneratedProductSlug } from '../src/pages/ProductEditor/productSlugAutofill.ts';

const apiSource = readFileSync(new URL('../src/shared/api/client.ts', import.meta.url), 'utf8');
const pageSource = readFileSync(
  new URL('../src/pages/ProductEditor/ProductEditorPage.tsx', import.meta.url),
  'utf8',
);

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
