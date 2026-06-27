import React from 'react';
import {
  addCartItem,
  toApiErrorMessage,
  type Product,
  type ProductVariant,
} from '../../shared/api';
import { displaySize, sortVariants } from '../../shared/utils/sizes';

const NO_COLOR_KEY = '__no_color__';

type ColorOption = {
  key: string;
  label: string;
};

type QuickCartPickerOptions = {
  requireAuth: () => boolean;
  onNotice: (message: string) => void;
};

function getVariantColorKey(variant: ProductVariant) {
  return variant.color?.trim() || NO_COLOR_KEY;
}

function getVariantColorLabel(variant: ProductVariant) {
  return variant.color?.trim() || 'Без цвета';
}

function getAvailableVariants(product: Product) {
  return sortVariants(
    product.variants.filter((variant) => variant.is_active && variant.available_quantity > 0),
    product.size_grid,
  );
}

function getColorOptions(variants: ProductVariant[]) {
  const options = new Map<string, ColorOption>();

  variants.forEach((variant) => {
    const key = getVariantColorKey(variant);
    if (!options.has(key)) {
      options.set(key, {
        key,
        label: getVariantColorLabel(variant),
      });
    }
  });

  return Array.from(options.values());
}

export function useQuickCartPicker({
  requireAuth,
  onNotice,
}: QuickCartPickerOptions) {
  const [pickerProduct, setPickerProduct] = React.useState<Product | null>(null);
  const [busyVariantId, setBusyVariantId] = React.useState<number | null>(null);
  const busyVariantIdsRef = React.useRef<Set<number>>(new Set());

  const addVariant = React.useCallback(
    async (product: Product, variant: ProductVariant) => {
      if (busyVariantIdsRef.current.has(variant.id)) {
        return;
      }

      busyVariantIdsRef.current.add(variant.id);
      setBusyVariantId(variant.id);
      try {
        await addCartItem(product.id, variant.id, 1);
        window.dispatchEvent(new Event('miniapp:cart-updated'));
        setPickerProduct(null);
        onNotice('Товар добавлен в корзину.');
      } catch (error) {
        onNotice(toApiErrorMessage(error));
      } finally {
        busyVariantIdsRef.current.delete(variant.id);
        setBusyVariantId(null);
      }
    },
    [onNotice],
  );

  const addToCart = React.useCallback(
    async (product: Product) => {
      if (!requireAuth()) {
        return;
      }

      const availableVariants = getAvailableVariants(product);
      if (availableVariants.length === 0) {
        onNotice('Нет доступных размеров.');
        return;
      }

      if (availableVariants.length === 1) {
        await addVariant(product, availableVariants[0]);
        return;
      }

      setPickerProduct(product);
    },
    [addVariant, onNotice, requireAuth],
  );

  const picker = pickerProduct ? (
    <QuickSizePicker
      busyVariantId={busyVariantId}
      product={pickerProduct}
      onClose={() => setPickerProduct(null)}
      onSelect={(variant) => void addVariant(pickerProduct, variant)}
    />
  ) : null;

  return {
    addToCart,
    picker,
  };
}

function QuickSizePicker({
  busyVariantId,
  product,
  onClose,
  onSelect,
}: {
  busyVariantId: number | null;
  product: Product;
  onClose: () => void;
  onSelect: (variant: ProductVariant) => void;
}) {
  const availableVariants = React.useMemo(() => getAvailableVariants(product), [product]);
  const colorOptions = React.useMemo(() => getColorOptions(availableVariants), [availableVariants]);
  const [selectedColorKey, setSelectedColorKey] = React.useState(
    () => colorOptions[0]?.key ?? NO_COLOR_KEY,
  );
  const showColorSelector = colorOptions.length > 1
    || colorOptions.some((option) => option.key !== NO_COLOR_KEY);
  const visibleVariants = showColorSelector
    ? availableVariants.filter((variant) => getVariantColorKey(variant) === selectedColorKey)
    : availableVariants;

  React.useEffect(() => {
    const nextColorKey = colorOptions[0]?.key ?? NO_COLOR_KEY;
    setSelectedColorKey(nextColorKey);
  }, [colorOptions, product.id]);

  React.useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') {
        onClose();
      }
    }

    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [onClose]);

  return (
    <div className="quick-size-sheet">
      <button
        className="quick-size-sheet__backdrop"
        type="button"
        aria-label="Закрыть выбор размера"
        onClick={onClose}
      />
      <section
        className="quick-size-sheet__panel"
        role="dialog"
        aria-modal="true"
        aria-labelledby="quick-size-title"
      >
        <header className="quick-size-sheet__header">
          <div>
            <h2 id="quick-size-title">Выберите размер</h2>
            <p>{product.brand ? `${product.brand} · ${product.name}` : product.name}</p>
          </div>
          <button type="button" aria-label="Закрыть" onClick={onClose}>
            ×
          </button>
        </header>

        {showColorSelector ? (
          <div className="quick-size-sheet__colors" aria-label="Доступные цвета">
            {colorOptions.map((option) => (
              <button
                className={selectedColorKey === option.key ? 'is-selected' : ''}
                key={option.key}
                type="button"
                onClick={() => setSelectedColorKey(option.key)}
              >
                {option.label}
              </button>
            ))}
          </div>
        ) : null}

        <div className="quick-size-sheet__sizes" aria-label="Доступные размеры">
          {visibleVariants.map((variant) => (
            <button
              className="quick-size-sheet__size"
              key={variant.id}
              type="button"
              disabled={busyVariantId !== null}
              onClick={() => onSelect(variant)}
            >
              {busyVariantId === variant.id ? '...' : displaySize(product.size_grid, variant.size, true)}
            </button>
          ))}
        </div>
      </section>
    </div>
  );
}
