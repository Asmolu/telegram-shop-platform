import assert from 'node:assert/strict';
import test from 'node:test';

import {
  allocateNumericVariantSkus,
  buildColorInputFromRows,
  buildVariantMatrixRows,
  countNewVariantMatrixRows,
  deriveSelectedSizesFromRows,
  generateVariantSku,
  getPersistedIncompatibleSizes,
  groupVariantMatrixRows,
  normalizeMatrixColorInput,
  sortSizesForGrid,
  toProductVariantPayload,
  validateVariantQuantities,
} from '../src/pages/ProductEditor/variantMatrix.ts';

function row(overrides = {}) {
  return {
    localId: 1,
    size: 'M',
    color: '',
    sku: '00001',
    stockQuantity: '0',
    reservedQuantity: '0',
    isActive: true,
    ...overrides,
  };
}

test('create matrix forms 9 rows with automatic safe SKU values', () => {
  const rows = buildVariantMatrixRows([], {
    sizeGrid: 'clothing_alpha',
    selectedSizes: ['M', 'L', 'XL'],
    colorInput: 'чёрный, белый, красный',
    productName: 'Moncler комплект',
    productSlug: 'moncler-komplekt',
    createLocalId: (() => {
      let id = 0;
      return () => {
        id += 1;
        return id;
      };
    })(),
  });

  assert.equal(rows.length, 9);
  assert.deepEqual(rows.map((variant) => variant.size).slice(0, 3), ['M', 'L', 'XL']);
  assert.deepEqual(rows.map((variant) => variant.sku), [
    '00001',
    '00002',
    '00003',
    '00004',
    '00005',
    '00006',
    '00007',
    '00008',
    '00009',
  ]);
  assert.ok(rows.every((variant) => /^[0-9]{5}$/.test(variant.sku)));
  assert.equal(new Set(rows.map((variant) => variant.sku)).size, 9);

  const editedRows = rows.map((variant, index) =>
    index === 0 ? { ...variant, stockQuantity: '5', reservedQuantity: '1' } : variant,
  );
  assert.deepEqual(validateVariantQuantities(editedRows), { ok: true });
});

test('duplicate colors are merged into one matrix block', () => {
  assert.equal(normalizeMatrixColorInput('чёрный, черный, ЧЁРНЫЙ'), 'чёрный');

  const rows = buildVariantMatrixRows([], {
    sizeGrid: 'clothing_alpha',
    selectedSizes: ['M', 'L'],
    colorInput: 'чёрный, черный, ЧЁРНЫЙ',
    productName: 'Hoodie',
    productSlug: 'hoodie',
  });
  const grouping = groupVariantMatrixRows(rows, {
    sizeGrid: 'clothing_alpha',
    selectedSizes: ['M', 'L'],
    colorInput: 'чёрный, черный, ЧЁРНЫЙ',
  });

  assert.equal(rows.length, 2);
  assert.equal(grouping.groups.length, 1);
  assert.equal(grouping.groups[0].rows.length, 2);
});

test('reserve above stock returns a validation error', () => {
  const result = validateVariantQuantities([
    row({ localId: 7, size: 'M', stockQuantity: '2', reservedQuantity: '3' }),
  ]);

  assert.deepEqual(result, {
    ok: false,
    localId: 7,
    reason: 'reservedAboveStock',
    size: 'M',
    color: '',
  });
});

test('edit mode groups existing variants and preserves IDs and SKUs', () => {
  const existingRows = [
    row({
      localId: 11,
      id: 11,
      size: 'M',
      color: 'чёрный',
      sku: 'saved-black-m',
      stockQuantity: '5',
    }),
    row({
      localId: 12,
      id: 12,
      size: 'L',
      color: 'белый',
      sku: 'saved-white-l',
      stockQuantity: '4',
    }),
  ];

  assert.equal(buildColorInputFromRows(existingRows), 'чёрный, белый');
  assert.deepEqual(deriveSelectedSizesFromRows('clothing_alpha', existingRows), ['M', 'L']);

  const rebuiltRows = buildVariantMatrixRows(existingRows, {
    sizeGrid: 'clothing_alpha',
    selectedSizes: ['M', 'L'],
    colorInput: 'чёрный, белый',
    productName: 'Saved product',
    productSlug: 'saved-product',
  });
  const grouping = groupVariantMatrixRows(rebuiltRows, {
    sizeGrid: 'clothing_alpha',
    selectedSizes: ['M', 'L'],
    colorInput: 'чёрный, белый',
  });

  assert.equal(rebuiltRows.find((variant) => variant.id === 11)?.sku, 'saved-black-m');
  assert.equal(rebuiltRows.find((variant) => variant.id === 12)?.sku, 'saved-white-l');
  assert.deepEqual(
    rebuiltRows.filter((variant) => variant.id).map((variant) => variant.id),
    [11, 12],
  );
  assert.equal(rebuiltRows.length, 4);
  assert.deepEqual(
    grouping.groups.map((group) => group.rows.some((variant) => variant.id)),
    [true, true],
  );
});

test('persisted variants outside the selected matrix are kept outside instead of being dropped', () => {
  const existingRows = [
    row({ localId: 21, id: 21, size: 'M', color: 'black', sku: 'saved-black-m' }),
    row({ localId: 22, id: 22, size: 'XL', color: 'black', sku: 'saved-black-xl' }),
  ];

  const rebuiltRows = buildVariantMatrixRows(existingRows, {
    sizeGrid: 'clothing_alpha',
    selectedSizes: ['M'],
    colorInput: 'black',
    productName: 'Saved product',
    productSlug: 'saved-product',
  });
  const grouping = groupVariantMatrixRows(rebuiltRows, {
    sizeGrid: 'clothing_alpha',
    selectedSizes: ['M'],
    colorInput: 'black',
  });

  assert.ok(rebuiltRows.some((variant) => variant.id === 22));
  assert.equal(grouping.outsideRows.length, 1);
  assert.equal(grouping.outsideRows[0].sku, 'saved-black-xl');
});

test('size grids sort and reject incompatible persisted sizes', () => {
  assert.deepEqual(sortSizesForGrid('clothing_alpha', ['XL', 'M', 'XS', 'ONE_SIZE', 'L']), [
    'XS',
    'M',
    'L',
    'XL',
    'ONE_SIZE',
  ]);
  assert.deepEqual(sortSizesForGrid('shoes_eu', ['46', '35', '40']), ['35', '40', '46']);
  assert.deepEqual(
    getPersistedIncompatibleSizes(
      [
        row({ id: 31, size: 'M' }),
        row({ localId: 32, size: '47' }),
      ],
      'shoes_eu',
    ),
    ['M'],
  );
});

test('variant payload keeps color null, SKU, stock, reserved, and active flag', () => {
  assert.deepEqual(
    toProductVariantPayload(
      row({
        id: 41,
        size: 'ONE_SIZE',
        color: '',
        sku: 'saved-no-color-one-size',
        stockQuantity: '8',
        reservedQuantity: '2',
        isActive: false,
      }),
    ),
    {
      size: 'ONE_SIZE',
      color: null,
      sku: 'saved-no-color-one-size',
      stock_quantity: 8,
      reserved_quantity: 2,
      is_active: false,
    },
  );
});

test('SKU generation starts at 00001 when no numeric SKU exists', () => {
  const existingSkus = new Set(['legacy-sku']);
  const sku = generateVariantSku({ existingSkus });

  assert.equal(sku, '00001');
  assert.equal(generateVariantSku({ existingSkus: new Set() }), '00001');
});

test('SKU generation skips existing numeric values', () => {
  const sku = generateVariantSku({
    existingSkus: new Set(['00001', '00002', '00004', 'legacy-sku']),
  });

  assert.equal(sku, '00003');
});

test('SKU generation preserves leading zeroes', () => {
  const existingSkus = new Set(
    Array.from({ length: 41 }, (_, index) => (index + 1).toString().padStart(5, '0')),
  );

  assert.equal(generateVariantSku({ existingSkus }), '00042');
});

test('batch SKU generation creates unique numeric values', () => {
  const generated = allocateNumericVariantSkus(new Set(['00001', '00003', 'random words']), 4);

  assert.deepEqual(generated, ['00002', '00004', '00005', '00006']);
  assert.equal(new Set(generated).size, generated.length);
  assert.ok(generated.every((sku) => /^[0-9]{5}$/.test(sku)));
});

test('SKU generation reports exhaustion instead of generating an invalid value', () => {
  const exhausted = new Set(
    Array.from({ length: 99999 }, (_, index) => (index + 1).toString().padStart(5, '0')),
  );

  assert.throws(
    () => generateVariantSku({ existingSkus: exhausted }),
    /00001-99999 is exhausted/,
  );
});

test('legacy nonnumeric SKUs do not block numeric generation', () => {
  assert.deepEqual(allocateNumericVariantSkus(new Set(['tshirt-white-m', 'MONCLER-M-WHITE']), 2), [
    '00001',
    '00002',
  ]);
});

test('matrix counts only new rows before requesting backend generated SKUs', () => {
  const currentRows = [
    row({ id: 1, size: 'M', color: 'black', sku: 'saved-black-m' }),
    row({ size: 'L', color: 'black', sku: '00012' }),
  ];

  assert.equal(
    countNewVariantMatrixRows(currentRows, {
      sizeGrid: 'clothing_alpha',
      selectedSizes: ['M', 'L', 'XL'],
      colorInput: 'black',
    }),
    1,
  );
});
