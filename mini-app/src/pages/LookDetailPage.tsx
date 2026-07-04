import React from 'react';
import {
  addLookToCart,
  getLook,
  getLookSimilarProducts,
  toApiErrorMessage,
  type LookDetail,
  type LookImage,
  type LookItem,
  type Product,
} from '../shared/api';
import { useAuth } from '../shared/auth/AuthProvider';
import { getAuthPath, Link, useRouter, withReturnTo } from '../shared/router/RouterProvider';
import { ErrorState, InlineNotice, PageLoader, SimilarProductsCarousel, TopBar } from '../shared/ui';
import { formatPrice } from '../shared/utils/format';
import { normalizeAssetUrl } from '../shared/utils/images';
import { getMotionAwareScrollBehavior } from '../shared/utils/motion';
import { runLockedAction } from '../shared/utils/actionLock';

const SIZE_ORDER = ['XXS', 'XS', 'S', 'M', 'L', 'XL', 'XXL', '3XL', 'ONE_SIZE'];

function canonicalLookPath(slug: string, currentPath: string) {
  const url = new URL(currentPath, window.location.origin);
  url.pathname = `/looks/${encodeURIComponent(slug)}`;
  return `${url.pathname}${url.search}`;
}

export function LookDetailPage() {
  const { currentPath, pathname, navigate } = useRouter();
  const { isAuthenticated } = useAuth();
  const slug = React.useMemo(() => decodeURIComponent(pathname.replace('/looks/', '').split('/')[0] ?? ''), [pathname]);
  const [look, setLook] = React.useState<LookDetail | null>(null);
  const [similarProducts, setSimilarProducts] = React.useState<Product[]>([]);
  const [similarProductsLoading, setSimilarProductsLoading] = React.useState(false);
  const [selectedItemIds, setSelectedItemIds] = React.useState<Set<number>>(new Set());
  const [selectedClothingSize, setSelectedClothingSize] = React.useState<string | null>(null);
  const [selectedFootwearSize, setSelectedFootwearSize] = React.useState<string | null>(null);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);
  const [notice, setNotice] = React.useState<string | null>(null);
  const [cartAction, setCartAction] = React.useState<'buy' | 'cart' | null>(null);
  const cartActionLock = React.useRef({ current: false });

  React.useEffect(() => {
    let cancelled = false;

    async function load() {
      if (!slug) {
        setError('Образ не найден');
        setLoading(false);
        return;
      }

      setLoading(true);
      setError(null);
      setNotice(null);
      try {
        const result = await getLook(slug);
        if (!cancelled) {
          const canonicalPath = canonicalLookPath(result.slug, currentPath);
          if (result.slug !== slug && canonicalPath !== currentPath) {
            navigate(canonicalPath, { replace: true });
          }
          setLook(result);
          setSelectedItemIds(new Set(getInitialSelectedItemIds(result)));
        }
      } catch (loadError) {
        if (!cancelled) {
          setError(toApiErrorMessage(loadError));
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    void load();
    return () => {
      cancelled = true;
    };
  }, [currentPath, navigate, slug]);

  React.useEffect(() => {
    if (!look) {
      setSimilarProducts([]);
      setSimilarProductsLoading(false);
      return;
    }

    let cancelled = false;
    const includedProductIds = new Set(look.items.map((item) => item.product_id));
    setSimilarProducts([]);
    setSimilarProductsLoading(true);

    getLookSimilarProducts(look.slug, 12, { networkImpact: 'local' })
      .then((result) => {
        if (!cancelled) {
          setSimilarProducts(
            result.items.filter((product) => !includedProductIds.has(product.id)),
          );
        }
      })
      .catch(() => {
        if (!cancelled) {
          setSimilarProducts([]);
        }
      })
      .finally(() => {
        if (!cancelled) {
          setSimilarProductsLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [look]);

  const selectedItems = React.useMemo(
    () => look?.items.filter((item) => selectedItemIds.has(item.look_item_id)) ?? [],
    [look, selectedItemIds],
  );
  const sizeState = React.useMemo(
    () => getSizeStateForSelection(selectedItems),
    [selectedItems],
  );
  const selectedPrice = React.useMemo(
    () => selectedItems.reduce((sum, item) => sum + getItemTotal(item), 0),
    [selectedItems],
  );
  const selectedOldPrice = React.useMemo(
    () => getSelectedOldPrice(selectedItems, selectedPrice),
    [selectedItems, selectedPrice],
  );
  const selectedItemsUnavailable = selectedItems.some((item) => !item.is_available);
  const noClothingSize = sizeState.requiresClothingSize && sizeState.clothingSizes.length === 0;
  const noFootwearSize = sizeState.requiresFootwearSize && sizeState.footwearSizes.length === 0;
  const selectedClothingSizeInvalid = sizeState.requiresClothingSize
    && (!selectedClothingSize || !sizeState.clothingSizes.includes(selectedClothingSize));
  const selectedFootwearSizeInvalid = sizeState.requiresFootwearSize
    && (!selectedFootwearSize || !sizeState.footwearSizes.includes(selectedFootwearSize));
  const ctaDisabled = cartAction !== null
    || selectedItems.length === 0
    || selectedItemsUnavailable
    || noClothingSize
    || noFootwearSize
    || selectedClothingSizeInvalid
    || selectedFootwearSizeInvalid;

  React.useEffect(() => {
    if (!sizeState.requiresClothingSize || sizeState.clothingSizes.length === 0) {
      if (selectedClothingSize !== null) {
        setSelectedClothingSize(null);
      }
      return;
    }

    if (selectedClothingSize && !sizeState.clothingSizes.includes(selectedClothingSize)) {
      setSelectedClothingSize(null);
    }
  }, [selectedClothingSize, sizeState.clothingSizes, sizeState.requiresClothingSize]);

  React.useEffect(() => {
    if (!sizeState.requiresFootwearSize || sizeState.footwearSizes.length === 0) {
      if (selectedFootwearSize !== null) {
        setSelectedFootwearSize(null);
      }
      return;
    }

    if (selectedFootwearSize && !sizeState.footwearSizes.includes(selectedFootwearSize)) {
      setSelectedFootwearSize(null);
    }
  }, [selectedFootwearSize, sizeState.footwearSizes, sizeState.requiresFootwearSize]);

  function toggleItem(item: LookItem) {
    setNotice(null);
    setSelectedItemIds((current) => {
      const next = new Set(current);
      if (next.has(item.look_item_id)) {
        if (next.size === 1) {
          setNotice('В образе должен остаться хотя бы один товар.');
          return current;
        }
        next.delete(item.look_item_id);
        return next;
      }
      next.add(item.look_item_id);
      return next;
    });
  }

  function getValidationNotice() {
    if (selectedItems.length === 0) {
      return 'Выберите хотя бы один товар.';
    }
    if (selectedItemsUnavailable) {
      return 'Один из выбранных товаров сейчас недоступен.';
    }
    if (noClothingSize) {
      return 'Нет доступного размера одежды для выбранных товаров.';
    }
    if (noFootwearSize) {
      return 'Нет доступного размера обуви для выбранных товаров.';
    }
    if (selectedClothingSizeInvalid) {
      return 'Выберите размер одежды.';
    }
    if (selectedFootwearSizeInvalid) {
      return 'Выберите размер обуви.';
    }
    return null;
  }

  async function runLookCartAction(action: 'buy' | 'cart') {
    if (!look) {
      return;
    }

    const validationMessage = getValidationNotice();
    if (validationMessage) {
      setNotice(validationMessage);
      return;
    }
    if (!isAuthenticated) {
      navigate(getAuthPath(currentPath));
      return;
    }

    await runLockedAction(cartActionLock.current, async () => {
      try {
        setCartAction(action);
        const response = await addLookToCart(look.slug, {
          selected_item_ids: Array.from(selectedItemIds),
          clothing_size: selectedClothingSize ?? null,
          footwear_size: selectedFootwearSize ?? null,
        });
        window.dispatchEvent(new Event('miniapp:cart-updated'));

        if (action === 'buy') {
          navigate(withReturnTo('/checkout', currentPath));
          return;
        }

        setNotice(response.message || 'Образ добавлен в корзину.');
      } catch (actionError) {
        setNotice(toApiErrorMessage(actionError));
      } finally {
        setCartAction(null);
      }
    });
  }

  if (loading) {
    return (
      <div className="page page--detail page--look-detail">
        <TopBar title="Образ" backFallback="/looks" />
        <PageLoader text="Загружаем образ..." />
      </div>
    );
  }

  if (error || !look) {
    return (
      <div className="page page--detail page--look-detail">
        <TopBar title="Образ" backFallback="/looks" />
        <ErrorState message={error ?? 'Образ не найден'} actionLabel="К образам" onAction={() => navigate('/looks')} />
      </div>
    );
  }

  const availabilityMessage = getValidationNotice();

  return (
    <div className="page page--detail page--look-detail">
      <TopBar title="Образ" backFallback="/looks" />

      {notice ? (
        <InlineNotice tone={notice.includes('добавлен') ? 'success' : 'warning'}>
          <span>{notice}</span>
          <button type="button" onClick={() => setNotice(null)}>
            ×
          </button>
        </InlineNotice>
      ) : null}

      <section className="product-gallery look-gallery">
        <LookImageCarousel title={look.title} images={look.images} />
      </section>

      <section className="detail-card product-info-card look-info-card">
        <div className="price-block">
          <div className="price-stack">
            <strong>{formatPrice(selectedPrice)}</strong>
            {selectedOldPrice ? (
              <span>
                <del>{formatPrice(selectedOldPrice)}</del>
              </span>
            ) : null}
          </div>
          <span>{availabilityMessage ?? 'Готов к добавлению'}</span>
        </div>
        <span className="look-detail-kicker">Образ</span>
        <h1 className="product-detail-title">{look.title}</h1>
        {look.description ? <p className="rating-line look-detail-description">{look.description}</p> : null}
      </section>

      {sizeState.requiresClothingSize ? (
        <LookSizeSelector
          ariaLabel="Доступные размеры одежды"
          emptyMessage="Нет доступного размера одежды для выбранных товаров."
          label="одежда"
          selectedSize={selectedClothingSize}
          sizes={sizeState.clothingSizes}
          title="Размер одежды"
          onSelect={setSelectedClothingSize}
        />
      ) : null}

      {sizeState.requiresFootwearSize ? (
        <LookSizeSelector
          ariaLabel="Доступные размеры обуви"
          emptyMessage="Нет доступного размера обуви для выбранных товаров."
          label="обувь"
          selectedSize={selectedFootwearSize}
          sizes={sizeState.footwearSizes}
          title="Размер обуви"
          onSelect={setSelectedFootwearSize}
        />
      ) : null}

      <section className="detail-card look-components-card">
        <div className="selector-heading">
          <h2>Состав образа</h2>
          <span>{selectedItems.length} / {look.items.length}</span>
        </div>
        <div className="look-components-list" data-swipe-back-ignore>
          {look.items.map((item) => (
            <LookComponentCard
              item={item}
              key={item.look_item_id}
              selected={selectedItemIds.has(item.look_item_id)}
              onToggle={() => toggleItem(item)}
            />
          ))}
        </div>
      </section>

      <section className="detail-card look-included-section">
        <h2>Товары в образе</h2>
        <div className="look-included-products" data-swipe-back-ignore>
          {look.items.map((item) => (
            <Link
              className="look-included-card"
              key={item.look_item_id}
              to={withReturnTo(`/product/${item.product_id}`, currentPath)}
            >
              <LookItemImage item={item} />
              <span>
                {item.brand ? <small>{item.brand}</small> : null}
                <strong>{item.product_name}</strong>
                <em>{formatPrice(item.price)}</em>
              </span>
            </Link>
          ))}
        </div>
      </section>

      <SimilarProductsCarousel
        loading={similarProductsLoading}
        products={similarProducts}
      />

      <div className="detail-cta detail-cta--bottom-attached">
        <div className="detail-cta__actions">
          <button
            className="secondary-button detail-cta__button detail-cta__button--buy"
            type="button"
            disabled={ctaDisabled}
            onClick={() => void runLookCartAction('buy')}
          >
            {cartAction === 'buy' ? 'Открываем...' : 'Купить сейчас'}
          </button>
          <button
            className="primary-button detail-cta__button detail-cta__button--cart"
            type="button"
            disabled={ctaDisabled}
            onClick={() => void runLookCartAction('cart')}
          >
            {cartAction === 'cart' ? 'Добавляем...' : 'В корзину'}
          </button>
        </div>
      </div>
    </div>
  );
}

function LookSizeSelector({
  ariaLabel,
  emptyMessage,
  label,
  selectedSize,
  sizes,
  title,
  onSelect,
}: {
  ariaLabel: string;
  emptyMessage: string;
  label: string;
  selectedSize: string | null;
  sizes: string[];
  title: string;
  onSelect: (size: string) => void;
}) {
  return (
    <section className="detail-card variant-selector-card look-size-card">
      <div className="selector-heading">
        <h2>{title}</h2>
        {selectedSize ? <span>{formatLookSize(selectedSize)}</span> : null}
      </div>
      {sizes.length > 0 ? (
        <div className="variant-carousel look-size-carousel" aria-label={ariaLabel}>
          {sizes.map((size) => (
            <button
              className={`variant-chip variant-chip--size variant-button ${selectedSize === size ? 'is-selected variant-chip--selected' : ''}`}
              key={size}
              type="button"
              onClick={() => onSelect(size)}
            >
              <strong>{formatLookSize(size)}</strong>
              <span>{label}</span>
            </button>
          ))}
        </div>
      ) : (
        <p className="muted-text">{emptyMessage}</p>
      )}
    </section>
  );
}

function LookImageCarousel({ images, title }: { images: LookImage[]; title: string }) {
  const trackRef = React.useRef<HTMLDivElement | null>(null);
  const [activeIndex, setActiveIndex] = React.useState(0);
  const [brokenImageIds, setBrokenImageIds] = React.useState<Set<string>>(new Set());
  const slides = React.useMemo(() => {
    const sorted = [...images].sort((left, right) => {
      if (left.is_primary !== right.is_primary) {
        return left.is_primary ? -1 : 1;
      }
      return left.position - right.position || left.id - right.id;
    });
    return sorted.length > 0 ? sorted : null;
  }, [images]);

  function handleScroll() {
    const track = trackRef.current;
    if (!track) {
      return;
    }
    const nextIndex = Math.round(track.scrollLeft / Math.max(track.clientWidth, 1));
    setActiveIndex(Math.min(Math.max(nextIndex, 0), (slides?.length ?? 1) - 1));
  }

  function scrollToSlide(index: number) {
    trackRef.current?.scrollTo({
      left: trackRef.current.clientWidth * index,
      behavior: getMotionAwareScrollBehavior(),
    });
  }

  if (!slides) {
    return (
      <div className="product-image-carousel product-image-carousel--detail look-image-carousel">
        <div className="image-fallback look-image-carousel__fallback">
          <span>{title.slice(0, 1).toUpperCase()}</span>
        </div>
      </div>
    );
  }

  return (
    <div className="product-image-carousel product-image-carousel--detail look-image-carousel">
      <div className="product-image-carousel__track" ref={trackRef} onScroll={handleScroll}>
        {slides.map((image, index) => {
          const imageUrl = normalizeAssetUrl(image.image_url ?? image.url ?? image.file_path);
          const imageId = String(image.id);
          return (
            <div className="product-image-carousel__slide" key={image.id}>
              {imageUrl && !brokenImageIds.has(imageId) ? (
                <img
                  src={imageUrl}
                  alt={image.alt_text ?? title}
                  width={1200}
                  height={1500}
                  loading={index === 0 ? 'eager' : 'lazy'}
                  decoding="async"
                  onError={() => {
                    setBrokenImageIds((current) => new Set(current).add(imageId));
                  }}
                />
              ) : (
                <div className="image-fallback">
                  <span>{title.slice(0, 1).toUpperCase()}</span>
                </div>
              )}
            </div>
          );
        })}
      </div>
      {slides.length > 1 ? (
        <>
          <div className="product-image-carousel__dots">
            {slides.map((image, index) => (
              <button
                className={activeIndex === index ? 'is-active' : ''}
                key={image.id}
                type="button"
                aria-label={`Фото ${index + 1}`}
                onClick={() => scrollToSlide(index)}
              />
            ))}
          </div>
          <span className="product-image-carousel__counter">
            {activeIndex + 1} / {slides.length}
          </span>
        </>
      ) : null}
    </div>
  );
}

function LookComponentCard({
  item,
  selected,
  onToggle,
}: {
  item: LookItem;
  selected: boolean;
  onToggle: () => void;
}) {
  return (
    <button
      className={`look-component-card ${selected ? 'is-selected' : ''} ${item.is_available ? '' : 'is-unavailable'}`}
      type="button"
      aria-pressed={selected}
      onClick={onToggle}
    >
      <LookItemImage item={item} />
      <span className="look-component-card__body">
        <span className="look-component-card__topline">
          {item.brand ? <small>{item.brand}</small> : null}
          <span className="look-component-card__check" aria-hidden="true">{selected ? '✓' : '+'}</span>
        </span>
        <strong>{item.product_name}</strong>
        <span>
          {getComponentSizeSummary(item)}
          {item.quantity > 1 ? ` · ${item.quantity} шт.` : ''}
        </span>
        <em>{formatPrice(getItemTotal(item))}</em>
      </span>
    </button>
  );
}

function LookItemImage({ item }: { item: LookItem }) {
  const imageUrl = normalizeAssetUrl(item.primary_image_url ?? item.product.image_url);
  return imageUrl ? (
    <img src={imageUrl} alt="" width={160} height={200} loading="lazy" decoding="async" />
  ) : (
    <span className="image-fallback">
      <span>{item.product_name.slice(0, 1).toUpperCase()}</span>
    </span>
  );
}

function getInitialSelectedItemIds(look: LookDetail) {
  const validIds = new Set(look.items.map((item) => item.look_item_id));
  const configured = look.default_selected_item_ids.filter((itemId) => validIds.has(itemId));
  if (configured.length > 0) {
    return configured;
  }

  const itemDefaults = look.items
    .filter((item) => item.is_default_selected)
    .map((item) => item.look_item_id);
  if (itemDefaults.length > 0) {
    return itemDefaults;
  }

  return look.items[0] ? [look.items[0].look_item_id] : [];
}

function getSizeStateForSelection(items: LookItem[]) {
  const clothingSizes = getAvailableSizesForSelection(items, 'CLOTHING');
  const footwearSizes = getAvailableSizesForSelection(items, 'FOOTWEAR');
  return {
    clothingSizes,
    footwearSizes,
    requiresClothingSize: items.some((item) => getLookItemSizeGroup(item) === 'CLOTHING'),
    requiresFootwearSize: items.some((item) => getLookItemSizeGroup(item) === 'FOOTWEAR'),
  };
}

function getAvailableSizesForSelection(items: LookItem[], group: 'CLOTHING' | 'FOOTWEAR') {
  const groupItems = items.filter((item) => getLookItemSizeGroup(item) === group);
  if (groupItems.length === 0) {
    return [];
  }

  const [first, ...rest] = groupItems.map((item) => (
    new Set(item.available_sizes.filter((size) => size && size !== 'ONE_SIZE'))
  ));
  if (!first) {
    return [];
  }

  return Array.from(first)
    .filter((size) => rest.every((set) => set.has(size)))
    .sort(sortLookSize);
}

function getLookItemSizeGroup(item: LookItem) {
  if (item.one_size || item.size_group === 'ONE_SIZE') {
    return 'ONE_SIZE';
  }
  return item.size_group === 'FOOTWEAR' ? 'FOOTWEAR' : 'CLOTHING';
}

function sortLookSize(left: string, right: string) {
  const leftNumber = Number(left);
  const rightNumber = Number(right);
  if (Number.isFinite(leftNumber) && Number.isFinite(rightNumber)) {
    return leftNumber - rightNumber;
  }
  const leftIndex = SIZE_ORDER.indexOf(left);
  const rightIndex = SIZE_ORDER.indexOf(right);
  const normalizedLeft = leftIndex < 0 ? SIZE_ORDER.length : leftIndex;
  const normalizedRight = rightIndex < 0 ? SIZE_ORDER.length : rightIndex;
  return normalizedLeft - normalizedRight || left.localeCompare(right, 'ru-RU');
}

function formatLookSize(size: string) {
  return size === 'ONE_SIZE' ? 'Единый размер' : size;
}

function getSizeSummary(sizes: string[]) {
  const normalized = sizes.filter((size) => size && size !== 'ONE_SIZE').sort(sortLookSize);
  return normalized.length > 0 ? normalized.join(' / ') : 'Нет размера';
}

function getComponentSizeSummary(item: LookItem) {
  const sizeGroup = getLookItemSizeGroup(item);
  if (sizeGroup === 'ONE_SIZE') {
    return 'Единый размер';
  }
  const prefix = sizeGroup === 'FOOTWEAR' ? 'Обувь' : 'Одежда';
  return `${prefix}: ${getSizeSummary(item.available_sizes)}`;
}

function getItemTotal(item: LookItem) {
  return toMoneyNumber(item.price) * Math.max(item.quantity, 1);
}

function getSelectedOldPrice(items: LookItem[], selectedPrice: number) {
  const hasOldPrice = items.some((item) => toMoneyNumber(item.old_price) > toMoneyNumber(item.price));
  if (!hasOldPrice) {
    return null;
  }
  const oldTotal = items.reduce((sum, item) => {
    const price = toMoneyNumber(item.price);
    const oldPrice = toMoneyNumber(item.old_price);
    return sum + (oldPrice > price ? oldPrice : price) * Math.max(item.quantity, 1);
  }, 0);
  return oldTotal > selectedPrice ? oldTotal : null;
}

function toMoneyNumber(value: string | number | null | undefined) {
  const numberValue = Number(value ?? 0);
  return Number.isFinite(numberValue) ? numberValue : 0;
}
