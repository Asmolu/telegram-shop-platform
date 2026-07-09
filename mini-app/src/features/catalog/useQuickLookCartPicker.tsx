import React from 'react';
import {
  addLookToCart,
  toApiErrorMessage,
  type LookCard,
} from '../../shared/api';

type QuickLookCartPickerOptions = {
  requireAuth: () => boolean;
  onNotice: (message: string) => void;
};

type PickerLook = LookCard;

export function useQuickLookCartPicker({
  requireAuth,
  onNotice,
}: QuickLookCartPickerOptions) {
  const [pickerLook, setPickerLook] = React.useState<PickerLook | null>(null);
  const [busy, setBusy] = React.useState(false);
  const busyRef = React.useRef(false);

  const addLook = React.useCallback(
    async (look: LookCard, sizes: { clothing_size?: string | null; footwear_size?: string | null } = {}) => {
      if (busyRef.current) {
        return;
      }
      if (!look.default_selected_item_ids.length) {
        onNotice('В образе нет выбранных товаров.');
        return;
      }

      busyRef.current = true;
      setBusy(true);
      try {
        await addLookToCart(look.slug, {
          selected_item_ids: look.default_selected_item_ids,
          clothing_size: sizes.clothing_size ?? null,
          footwear_size: sizes.footwear_size ?? null,
        });
        window.dispatchEvent(new Event('miniapp:cart-updated'));
        setPickerLook(null);
        onNotice('Образ добавлен в корзину.');
      } catch (error) {
        onNotice(toApiErrorMessage(error));
      } finally {
        busyRef.current = false;
        setBusy(false);
      }
    },
    [onNotice],
  );

  const addToCart = React.useCallback(
    async (look: LookCard) => {
      if (!requireAuth()) {
        return;
      }
      if (!look.is_available) {
        onNotice('Нет доступного размера для образа.');
        return;
      }
      if (!look.requires_clothing_size && !look.requires_footwear_size) {
        await addLook(look);
        return;
      }
      setPickerLook(look);
    },
    [addLook, onNotice, requireAuth],
  );

  const picker = pickerLook ? (
    <QuickLookSizePicker
      busy={busy}
      look={pickerLook}
      onClose={() => setPickerLook(null)}
      onSubmit={(sizes) => void addLook(pickerLook, sizes)}
    />
  ) : null;

  return { addToCart, picker };
}

function QuickLookSizePicker({
  busy,
  look,
  onClose,
  onSubmit,
}: {
  busy: boolean;
  look: PickerLook;
  onClose: () => void;
  onSubmit: (sizes: { clothing_size?: string | null; footwear_size?: string | null }) => void;
}) {
  const [clothingSize, setClothingSize] = React.useState(look.available_clothing_sizes[0] ?? '');
  const [footwearSize, setFootwearSize] = React.useState(look.available_footwear_sizes[0] ?? '');

  React.useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') {
        onClose();
      }
    }
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [onClose]);

  const clothingUnavailable = look.requires_clothing_size && look.available_clothing_sizes.length === 0;
  const footwearUnavailable = look.requires_footwear_size && look.available_footwear_sizes.length === 0;
  const disabled = busy || clothingUnavailable || footwearUnavailable;

  return (
    <div className="quick-size-sheet">
      <button
        className="quick-size-sheet__backdrop"
        type="button"
        aria-label="Закрыть выбор размера"
        onClick={onClose}
      />
      <section
        className="quick-size-sheet__panel quick-size-sheet__panel--look"
        role="dialog"
        aria-modal="true"
        aria-labelledby="quick-look-size-title"
      >
        <header className="quick-size-sheet__header">
          <div>
            <h2 id="quick-look-size-title">Выберите размер</h2>
            <p>{look.title}</p>
          </div>
          <button type="button" aria-label="Закрыть" onClick={onClose}>
            ×
          </button>
        </header>

        {look.requires_clothing_size ? (
          <SizeGroup
            label="Размер одежды"
            sizes={look.available_clothing_sizes}
            value={clothingSize}
            onChange={setClothingSize}
            emptyMessage="Нет доступного размера одежды."
          />
        ) : null}
        {look.requires_footwear_size ? (
          <SizeGroup
            label="Размер обуви"
            sizes={look.available_footwear_sizes}
            value={footwearSize}
            onChange={setFootwearSize}
            emptyMessage="Нет доступного размера обуви."
          />
        ) : null}

        <button
          className="primary-button full-width"
          type="button"
          disabled={disabled}
          onClick={() =>
            onSubmit({
              clothing_size: look.requires_clothing_size ? clothingSize : null,
              footwear_size: look.requires_footwear_size ? footwearSize : null,
            })
          }
        >
          {busy ? 'Добавляем...' : 'Добавить в корзину'}
        </button>
      </section>
    </div>
  );
}

function SizeGroup({
  label,
  sizes,
  value,
  onChange,
  emptyMessage,
}: {
  label: string;
  sizes: string[];
  value: string;
  onChange: (value: string) => void;
  emptyMessage: string;
}) {
  return (
    <div className="quick-look-size-group">
      <span>{label}</span>
      {sizes.length > 0 ? (
        <div className="quick-size-sheet__sizes" aria-label={label}>
          {sizes.map((size) => (
            <button
              className={`quick-size-sheet__size ${value === size ? 'is-selected' : ''}`}
              key={size}
              type="button"
              onClick={() => onChange(size)}
            >
              {size}
            </button>
          ))}
        </div>
      ) : (
        <p className="form-error">{emptyMessage}</p>
      )}
    </div>
  );
}
