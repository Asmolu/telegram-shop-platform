import type { ProductSizeGrid, ProductVariantPayload } from '../../shared/api';

export const CLOTHING_ALPHA_SIZES = ['XS', 'S', 'M', 'L', 'XL', 'XXL', '3XL', 'ONE_SIZE'] as const;
export const SHOES_EU_SIZES = [
  '35',
  '36',
  '37',
  '38',
  '39',
  '40',
  '41',
  '42',
  '43',
  '44',
  '45',
  '46',
] as const;
export const SHOES_RU_SIZES = SHOES_EU_SIZES;

const NO_COLOR_KEY = '__no_color__';
const NUMERIC_SKU_MIN = 1;
const NUMERIC_SKU_MAX = 99999;
const NUMERIC_SKU_PATTERN = /^[0-9]{5}$/;

export interface VariantMatrixRow {
  localId: number;
  id?: number;
  size: string;
  color: string;
  sku: string;
  stockQuantity: string;
  reservedQuantity: string;
  isActive: boolean;
  remove?: boolean;
}

export interface MatrixColor {
  key: string;
  label: string;
  value: string;
  isNoColor: boolean;
}

export interface MatrixGroup<Row extends VariantMatrixRow = VariantMatrixRow> {
  color: MatrixColor;
  rows: Row[];
}

export interface MatrixGrouping<Row extends VariantMatrixRow = VariantMatrixRow> {
  groups: Array<MatrixGroup<Row>>;
  outsideRows: Row[];
}

export type QuantityValidationResult =
  | { ok: true }
  | {
      ok: false;
      localId: number;
      reason: 'integer' | 'negative' | 'reservedAboveStock';
      size: string;
      color: string;
    };

interface MatrixBuildOptions {
  sizeGrid: ProductSizeGrid;
  selectedSizes: string[];
  colorInput: string;
  productName: string;
  productSlug: string;
  createLocalId?: () => number;
  generatedSkus?: string[];
}

interface SkuOptions {
  existingSkus: Set<string>;
}

export function allowedSizes(sizeGrid: ProductSizeGrid): readonly string[] {
  if (sizeGrid === 'shoes_eu') return SHOES_EU_SIZES;
  if (sizeGrid === 'shoes_ru') return SHOES_RU_SIZES;
  return CLOTHING_ALPHA_SIZES;
}

export function normalizeSizeForGrid(sizeGrid: ProductSizeGrid, value: string): string {
  const normalized = sizeGrid === 'clothing_alpha' ? value.trim().toUpperCase() : value.trim();
  return allowedSizes(sizeGrid).includes(normalized) ? normalized : '';
}

export function sortSizesForGrid(sizeGrid: ProductSizeGrid, sizes: string[]): string[] {
  const order = allowedSizes(sizeGrid);
  const uniqueSizes = Array.from(
    new Set(sizes.map((size) => normalizeSizeForGrid(sizeGrid, size)).filter(Boolean)),
  );

  return uniqueSizes.sort((left, right) => {
    const leftIndex = order.indexOf(left);
    const rightIndex = order.indexOf(right);
    if (leftIndex !== rightIndex) return leftIndex - rightIndex;
    return left.localeCompare(right);
  });
}

export function parseMatrixColors(input: string): MatrixColor[] {
  const colors = input
    .split(',')
    .map((color) => color.trim())
    .filter(Boolean);

  const deduped = new Map<string, MatrixColor>();
  colors.forEach((color) => {
    const key = normalizeVariantColorKey(color) || NO_COLOR_KEY;
    if (!deduped.has(key)) {
      deduped.set(key, {
        key,
        label: color,
        value: color,
        isNoColor: false,
      });
    }
  });

  if (deduped.size === 0) {
    return [
      {
        key: NO_COLOR_KEY,
        label: '',
        value: '',
        isNoColor: true,
      },
    ];
  }

  return Array.from(deduped.values());
}

export function normalizeMatrixColorInput(input: string): string {
  return parseMatrixColors(input)
    .filter((color) => !color.isNoColor)
    .map((color) => color.value)
    .join(', ');
}

export function buildColorInputFromRows(rows: VariantMatrixRow[]): string {
  return parseMatrixColors(rows.map((row) => row.color).filter(Boolean).join(', '))
    .filter((color) => !color.isNoColor)
    .map((color) => color.value)
    .join(', ');
}

export function deriveSelectedSizesFromRows(
  sizeGrid: ProductSizeGrid,
  rows: VariantMatrixRow[],
): string[] {
  return sortSizesForGrid(
    sizeGrid,
    rows.filter((row) => !row.remove).map((row) => row.size),
  );
}

export function getIncompatibleSizes(
  rows: VariantMatrixRow[],
  sizeGrid: ProductSizeGrid,
  persistedOnly = false,
): string[] {
  const incompatible = rows
    .filter((row) => !row.remove && (!persistedOnly || row.id) && row.size.trim())
    .map((row) => row.size.trim())
    .filter((size) => !normalizeSizeForGrid(sizeGrid, size));

  return Array.from(new Set(incompatible));
}

export function getPersistedIncompatibleSizes(
  rows: VariantMatrixRow[],
  sizeGrid: ProductSizeGrid,
): string[] {
  return getIncompatibleSizes(rows, sizeGrid, true);
}

export function buildVariantMatrixRows<Row extends VariantMatrixRow>(
  currentRows: Row[],
  options: MatrixBuildOptions,
): Row[] {
  const matrixColors = parseMatrixColors(options.colorInput);
  const selectedSizes = sortSizesForGrid(options.sizeGrid, options.selectedSizes);
  const wantedKeys = new Set<string>();
  const currentByKey = new Map<string, Row>();
  const existingSkus = new Set(
    currentRows.map((row) => row.sku.trim().toLowerCase()).filter(Boolean),
  );

  currentRows.forEach((row) => {
    if (row.remove) return;
    const key = getVariantKey(row.size, row.color, options.sizeGrid);
    if (key && !currentByKey.has(key)) {
      currentByKey.set(key, row);
    }
  });

  const nextRows: Row[] = [];
  let generatedSkuIndex = 0;
  matrixColors.forEach((color) => {
    selectedSizes.forEach((size) => {
      const key = getVariantKey(size, color.value, options.sizeGrid);
      if (!key) return;
      wantedKeys.add(key);
      const existingRow = currentByKey.get(key);
      if (existingRow) {
        nextRows.push(existingRow);
        return;
      }

      const sku = options.generatedSkus?.[generatedSkuIndex] ?? generateVariantSku({ existingSkus });
      generatedSkuIndex += 1;
      existingSkus.add(sku.toLowerCase());
      nextRows.push({
        localId: options.createLocalId?.() ?? createLocalId(),
        size,
        color: color.value,
        sku,
        stockQuantity: '0',
        reservedQuantity: '0',
        isActive: true,
      } as Row);
    });
  });

  currentRows.forEach((row) => {
    if (row.remove) {
      nextRows.push(row);
      return;
    }
    const key = getVariantKey(row.size, row.color, options.sizeGrid);
    if (row.id && (!key || !wantedKeys.has(key))) {
      nextRows.push(row);
    }
  });

  return nextRows;
}

export function countNewVariantMatrixRows(
  currentRows: VariantMatrixRow[],
  options: Pick<MatrixBuildOptions, 'sizeGrid' | 'selectedSizes' | 'colorInput'>,
): number {
  const matrixColors = parseMatrixColors(options.colorInput);
  const selectedSizes = sortSizesForGrid(options.sizeGrid, options.selectedSizes);
  const currentKeys = new Set<string>();

  currentRows.forEach((row) => {
    if (row.remove) return;
    const key = getVariantKey(row.size, row.color, options.sizeGrid);
    if (key) {
      currentKeys.add(key);
    }
  });

  let count = 0;
  matrixColors.forEach((color) => {
    selectedSizes.forEach((size) => {
      const key = getVariantKey(size, color.value, options.sizeGrid);
      if (key && !currentKeys.has(key)) {
        count += 1;
      }
    });
  });

  return count;
}

export function regenerateNewSkusForRows<Row extends VariantMatrixRow>(
  rows: Row[],
  options: Pick<MatrixBuildOptions, 'generatedSkus'> = {},
): Row[] {
  const existingSkus = new Set(
    rows
      .filter((row) => row.id || row.remove)
      .map((row) => row.sku.trim().toLowerCase())
      .filter(Boolean),
  );
  let generatedSkuIndex = 0;

  return rows.map((row) => {
    if (row.id || row.remove || !row.size.trim()) {
      return row;
    }

    const sku = options.generatedSkus?.[generatedSkuIndex] ?? generateVariantSku({ existingSkus });
    generatedSkuIndex += 1;
    existingSkus.add(sku.toLowerCase());
    return { ...row, sku };
  });
}

export function groupVariantMatrixRows<Row extends VariantMatrixRow>(
  rows: Row[],
  options: Pick<MatrixBuildOptions, 'sizeGrid' | 'selectedSizes' | 'colorInput'>,
): MatrixGrouping<Row> {
  const colors = parseMatrixColors(options.colorInput);
  const selectedSizes = sortSizesForGrid(options.sizeGrid, options.selectedSizes);
  const sizeSet = new Set(selectedSizes);
  const colorSet = new Set(colors.map((color) => color.key));
  const groups = colors.map((color) => ({ color, rows: [] as Row[] }));
  const groupByColor = new Map(groups.map((group) => [group.color.key, group]));
  const outsideRows: Row[] = [];

  rows
    .filter((row) => !row.remove)
    .forEach((row) => {
      const normalizedSize = normalizeSizeForGrid(options.sizeGrid, row.size);
      const colorKey = getColorKey(row.color);
      const group = groupByColor.get(colorKey);
      if (!normalizedSize || !sizeSet.has(normalizedSize) || !group || !colorSet.has(colorKey)) {
        outsideRows.push(row);
        return;
      }
      group.rows.push(row);
    });

  groups.forEach((group) => {
    group.rows.sort((left, right) => {
      const leftIndex = selectedSizes.indexOf(normalizeSizeForGrid(options.sizeGrid, left.size));
      const rightIndex = selectedSizes.indexOf(normalizeSizeForGrid(options.sizeGrid, right.size));
      return leftIndex - rightIndex;
    });
  });

  outsideRows.sort((left, right) => {
    const leftSize = normalizeSizeForGrid(options.sizeGrid, left.size) || left.size;
    const rightSize = normalizeSizeForGrid(options.sizeGrid, right.size) || right.size;
    const leftIndex = selectedSizes.indexOf(leftSize);
    const rightIndex = selectedSizes.indexOf(rightSize);
    if (leftIndex !== rightIndex) return leftIndex - rightIndex;
    return leftSize.localeCompare(rightSize);
  });

  return { groups, outsideRows };
}

export function validateVariantQuantities(rows: VariantMatrixRow[]): QuantityValidationResult {
  for (const row of rows) {
    if (row.remove || (!row.size.trim() && !row.sku.trim())) {
      continue;
    }

    const stock = parseIntegerInput(row.stockQuantity);
    const reserved = parseIntegerInput(row.reservedQuantity);
    const context = {
      localId: row.localId,
      size: row.size,
      color: row.color,
    };

    if (stock === null || reserved === null) {
      return { ok: false, reason: 'integer', ...context };
    }
    if (stock < 0 || reserved < 0) {
      return { ok: false, reason: 'negative', ...context };
    }
    if (reserved > stock) {
      return { ok: false, reason: 'reservedAboveStock', ...context };
    }
  }

  return { ok: true };
}

export function toProductVariantPayload(row: VariantMatrixRow): ProductVariantPayload | null {
  if (row.remove || (!row.size.trim() && !row.sku.trim())) {
    return null;
  }

  return {
    size: row.size.trim(),
    color: row.color.trim() || null,
    sku: row.sku.trim(),
    stock_quantity: Number(row.stockQuantity || 0),
    reserved_quantity: Number(row.reservedQuantity || 0),
    is_active: row.isActive,
  };
}

export function hasDuplicateVariantKeys(rows: VariantMatrixRow[]): boolean {
  const keys = rows
    .filter((row) => !row.remove && row.size.trim())
    .map((row) => `${row.size.trim().toUpperCase()}::${getColorKey(row.color)}`);
  return new Set(keys).size !== keys.length;
}

export function normalizeVariantColorKey(color: string): string {
  return color.trim().replace(/\s+/g, ' ').toLocaleLowerCase('ru-RU').replace(/\u0451/g, '\u0435');
}

export function generateVariantSku(options: SkuOptions): string {
  return allocateNumericVariantSkus(options.existingSkus, 1)[0];
}

export function allocateNumericVariantSkus(existingSkus: Set<string>, count: number): string[] {
  const usedNumbers = new Set<number>();

  existingSkus.forEach((sku) => {
    if (!NUMERIC_SKU_PATTERN.test(sku)) {
      return;
    }
    const value = Number(sku);
    if (value >= NUMERIC_SKU_MIN && value <= NUMERIC_SKU_MAX) {
      usedNumbers.add(value);
    }
  });

  const generated: string[] = [];
  for (let value = NUMERIC_SKU_MIN; value <= NUMERIC_SKU_MAX; value += 1) {
    if (usedNumbers.has(value)) {
      continue;
    }
    usedNumbers.add(value);
    generated.push(formatNumericVariantSku(value));
    if (generated.length === count) {
      return generated;
    }
  }

  throw new Error('Numeric SKU range 00001-99999 is exhausted.');
}

function getVariantKey(
  size: string,
  color: string,
  sizeGrid: ProductSizeGrid,
): string | null {
  const normalizedSize = normalizeSizeForGrid(sizeGrid, size);
  if (!normalizedSize) {
    return null;
  }

  return `${normalizedSize}::${getColorKey(color)}`;
}

function getColorKey(color: string): string {
  return normalizeVariantColorKey(color) || NO_COLOR_KEY;
}

function formatNumericVariantSku(value: number): string {
  return value.toString().padStart(5, '0');
}

function createLocalId(): number {
  return Date.now() + Math.random();
}

function parseIntegerInput(value: string): number | null {
  if (!/^\d+$/.test(value.trim())) {
    return null;
  }
  const parsed = Number(value);
  return Number.isSafeInteger(parsed) ? parsed : null;
}
