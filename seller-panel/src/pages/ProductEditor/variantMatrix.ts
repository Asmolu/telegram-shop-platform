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
const SKU_MAX_LENGTH = 100;

const CYRILLIC_TO_LATIN: Record<string, string> = {
  '\u0430': 'a',
  '\u0431': 'b',
  '\u0432': 'v',
  '\u0433': 'g',
  '\u0434': 'd',
  '\u0435': 'e',
  '\u0451': 'e',
  '\u0436': 'zh',
  '\u0437': 'z',
  '\u0438': 'i',
  '\u0439': 'y',
  '\u043a': 'k',
  '\u043b': 'l',
  '\u043c': 'm',
  '\u043d': 'n',
  '\u043e': 'o',
  '\u043f': 'p',
  '\u0440': 'r',
  '\u0441': 's',
  '\u0442': 't',
  '\u0443': 'u',
  '\u0444': 'f',
  '\u0445': 'h',
  '\u0446': 'ts',
  '\u0447': 'ch',
  '\u0448': 'sh',
  '\u0449': 'sch',
  '\u044a': '',
  '\u044b': 'y',
  '\u044c': '',
  '\u044d': 'e',
  '\u044e': 'yu',
  '\u044f': 'ya',
};

const COLOR_SKU_ALIASES: Record<string, string> = {
  '\u0431\u0435\u0436\u0435\u0432\u044b\u0439': 'beige',
  '\u0431\u0435\u043b\u044b\u0439': 'white',
  '\u0431\u043e\u0440\u0434\u043e\u0432\u044b\u0439': 'burgundy',
  '\u0433\u043e\u043b\u0443\u0431\u043e\u0439': 'light-blue',
  '\u0436\u0435\u043b\u0442\u044b\u0439': 'yellow',
  '\u0436\u0451\u043b\u0442\u044b\u0439': 'yellow',
  '\u0437\u0435\u043b\u0435\u043d\u044b\u0439': 'green',
  '\u0437\u0435\u043b\u0451\u043d\u044b\u0439': 'green',
  '\u0437\u043e\u043b\u043e\u0442\u043e\u0439': 'gold',
  '\u043a\u043e\u0440\u0438\u0447\u043d\u0435\u0432\u044b\u0439': 'brown',
  '\u043a\u0440\u0430\u0441\u043d\u044b\u0439': 'red',
  '\u043c\u043e\u043b\u043e\u0447\u043d\u044b\u0439': 'milk',
  '\u043e\u0440\u0430\u043d\u0436\u0435\u0432\u044b\u0439': 'orange',
  '\u0440\u043e\u0437\u043e\u0432\u044b\u0439': 'pink',
  '\u0441\u0435\u0440\u044b\u0439': 'gray',
  '\u0441\u0435\u0440\u0435\u0431\u0440\u044f\u043d\u044b\u0439': 'silver',
  '\u0441\u0438\u043d\u0438\u0439': 'blue',
  '\u0444\u0438\u043e\u043b\u0435\u0442\u043e\u0432\u044b\u0439': 'purple',
  '\u0447\u0435\u0440\u043d\u044b\u0439': 'black',
  '\u0447\u0451\u0440\u043d\u044b\u0439': 'black',
};

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
  randomSuffix?: () => string;
}

interface SkuOptions {
  productName: string;
  productSlug: string;
  color: string;
  size: string;
  existingSkus: Set<string>;
  randomSuffix?: () => string;
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

      const sku = generateVariantSku({
        productName: options.productName,
        productSlug: options.productSlug,
        color: color.value,
        size,
        existingSkus,
        randomSuffix: options.randomSuffix,
      });
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

export function regenerateNewSkusForRows<Row extends VariantMatrixRow>(
  rows: Row[],
  options: Pick<MatrixBuildOptions, 'productName' | 'productSlug' | 'randomSuffix'>,
): Row[] {
  const existingSkus = new Set(
    rows
      .filter((row) => row.id || row.remove)
      .map((row) => row.sku.trim().toLowerCase())
      .filter(Boolean),
  );

  return rows.map((row) => {
    if (row.id || row.remove || !row.size.trim()) {
      return row;
    }

    const sku = generateVariantSku({
      productName: options.productName,
      productSlug: options.productSlug,
      color: row.color,
      size: row.size,
      existingSkus,
      randomSuffix: options.randomSuffix,
    });
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
  const productKey =
    asciiSlug(options.productSlug, '') || asciiSlug(options.productName, '') || 'product';
  const colorKey = getSkuColorKey(options.color);
  const sizeKey = asciiSlug(options.size, 'size');
  const base = [productKey.slice(0, 42), colorKey.slice(0, 24), sizeKey.slice(0, 12)]
    .filter(Boolean)
    .join('-')
    .slice(0, 88)
    .replace(/-+$/g, '');

  for (let attempt = 0; attempt < 20; attempt += 1) {
    const suffix = sanitizeSkuPart(options.randomSuffix?.() ?? defaultRandomSuffix()).slice(0, 8);
    const sku = trimSku(`${base}-${suffix || defaultRandomSuffix()}`);
    if (!options.existingSkus.has(sku.toLowerCase())) {
      return sku;
    }
  }

  return trimSku(`${base}-${Date.now().toString(16).slice(-8)}`);
}

export function asciiSlug(value: string, fallback = 'product'): string {
  const transliterated = value
    .trim()
    .toLocaleLowerCase('ru-RU')
    .split('')
    .map((char) => CYRILLIC_TO_LATIN[char] ?? char)
    .join('')
    .normalize('NFKD')
    .replace(/[\u0300-\u036f]/g, '');
  const slug = sanitizeSkuPart(transliterated);
  return slug || fallback;
}

function getSkuColorKey(color: string): string {
  const normalized = normalizeVariantColorKey(color);
  if (!normalized) {
    return 'no-color';
  }

  return COLOR_SKU_ALIASES[normalized] ?? asciiSlug(normalized, 'color');
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

function sanitizeSkuPart(value: string): string {
  return value
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .replace(/-+/g, '-');
}

function trimSku(sku: string): string {
  return sku.slice(0, SKU_MAX_LENGTH).replace(/-+$/g, '');
}

function defaultRandomSuffix(): string {
  const random = new Uint8Array(3);
  globalThis.crypto?.getRandomValues(random);
  if (random.some((byte) => byte > 0)) {
    return Array.from(random)
      .map((byte) => byte.toString(16).padStart(2, '0'))
      .join('');
  }

  return Math.floor(Math.random() * 0xffffff)
    .toString(16)
    .padStart(6, '0');
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
