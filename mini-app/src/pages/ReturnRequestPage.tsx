import React from 'react';
import {
  createReturnRequest,
  getOrder,
  getReturnEligibility,
  toApiErrorMessage,
  type Order,
  type ReturnEligibility,
  type ReturnEligibilityItem,
} from '../shared/api';
import { useAuth } from '../shared/auth/AuthProvider';
import { getAuthPath, getNumericRouteParam, useRouter } from '../shared/router/RouterProvider';
import { EmptyState, ErrorState, PageLoader, TopBar } from '../shared/ui';
import { normalizeAssetUrl } from '../shared/utils/images';

const MAX_RETURN_FILES = 5;
const MAX_RETURN_FILE_SIZE = 20 * 1024 * 1024;
const RETURN_FILE_TYPES = new Set([
  'image/jpeg',
  'image/png',
  'image/webp',
  'video/mp4',
  'video/webm',
  'video/quicktime',
]);

export function ReturnRequestPage() {
  const { currentPath, pathname, navigate } = useRouter();
  const { isAuthenticated } = useAuth();
  const orderId = getNumericRouteParam(pathname, '/orders/');
  const backPath = orderId ? `/order-success/${orderId}` : '/cart?tab=orders';
  const [order, setOrder] = React.useState<Order | null>(null);
  const [eligibility, setEligibility] = React.useState<ReturnEligibility | null>(null);
  const [selectedItems, setSelectedItems] = React.useState<Record<number, boolean>>({});
  const [quantities, setQuantities] = React.useState<Record<number, number>>({});
  const [reason, setReason] = React.useState('');
  const [comment, setComment] = React.useState('');
  const [files, setFiles] = React.useState<File[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [submitting, setSubmitting] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [submitError, setSubmitError] = React.useState<string | null>(null);
  const [successMessage, setSuccessMessage] = React.useState<string | null>(null);

  React.useEffect(() => {
    let cancelled = false;

    async function load() {
      if (!isAuthenticated || !orderId) {
        setLoading(false);
        return;
      }

      setLoading(true);
      setError(null);
      try {
        const [orderResult, eligibilityResult] = await Promise.all([
          getOrder(orderId),
          getReturnEligibility(orderId),
        ]);
        if (cancelled) return;
        setOrder(orderResult);
        setEligibility(eligibilityResult);
      } catch (loadError) {
        if (!cancelled) setError(toApiErrorMessage(loadError));
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    void load();
    return () => {
      cancelled = true;
    };
  }, [isAuthenticated, orderId]);

  const eligibleItems = React.useMemo(
    () => eligibility?.items.filter((item) => item.eligible) ?? [],
    [eligibility],
  );

  if (!isAuthenticated) {
    return (
      <div className="page">
        <TopBar title="Оформить возврат" backFallback={backPath} />
        <EmptyState
          title="Нужен вход через Telegram"
          message="Оформление возврата доступно после входа."
          actionLabel="Войти"
          onAction={() => navigate(getAuthPath(currentPath))}
        />
      </div>
    );
  }

  if (successMessage) {
    return (
      <div className="page return-page">
        <TopBar title="Оформить возврат" backFallback={backPath} />
        <section className="success-card return-success-card">
          <div className="success-icon">✓</div>
          <h1>{successMessage}</h1>
          <button className="primary-button" type="button" onClick={() => navigate(backPath)}>
            Вернуться к заказу
          </button>
        </section>
      </div>
    );
  }

  return (
    <div className="page return-page">
      <TopBar title="Оформить возврат" backFallback={backPath} />
      {loading ? <PageLoader text="Проверяем возврат..." /> : null}
      {!loading && error ? <ErrorState message={error} /> : null}
      {!loading && !error && eligibility && !eligibility.eligible ? (
        <EmptyState
          title="Возврат недоступен"
          message={eligibility.message}
          actionLabel="Вернуться к заказу"
          onAction={() => navigate(backPath)}
        />
      ) : null}
      {!loading && !error && eligibility?.eligible && eligibleItems.length === 0 ? (
        <EmptyState
          title="Нет товаров для возврата"
          message="В этом заказе нет позиций, доступных для возврата."
          actionLabel="Вернуться к заказу"
          onAction={() => navigate(backPath)}
        />
      ) : null}
      {!loading && !error && eligibility?.eligible && eligibleItems.length > 0 ? (
        <form className="return-form" onSubmit={submitReturnRequest}>
          <section className="order-detail-section return-form__section">
            <h2>{order?.order_number ? `Заказ ${order.order_number}` : 'Товары'}</h2>
            <div className="return-item-list">
              {eligibleItems.map((item) => (
                <ReturnItemCard
                  item={item}
                  key={item.order_item_id}
                  quantity={quantities[item.order_item_id] ?? 1}
                  selected={Boolean(selectedItems[item.order_item_id])}
                  onQuantityChange={(quantity) => updateQuantity(item.order_item_id, quantity)}
                  onToggle={() => toggleItem(item.order_item_id)}
                />
              ))}
            </div>
          </section>

          <section className="order-detail-section return-form__section">
            <label>
              <span>Причина</span>
              <textarea
                required
                rows={4}
                value={reason}
                placeholder="Например: не подошёл размер, цвет отличается, обнаружен дефект"
                onChange={(event) => {
                  setReason(event.target.value);
                  setSubmitError(null);
                }}
              />
            </label>
            <label>
              <span>Комментарий</span>
              <textarea
                rows={3}
                value={comment}
                placeholder="Добавьте детали, если нужно"
                onChange={(event) => setComment(event.target.value)}
              />
            </label>
          </section>

          <section className="order-detail-section return-form__section">
            <label className="return-upload">
              <span>Фото или видео</span>
              <input
                accept="image/jpeg,image/png,image/webp,video/mp4,video/webm,video/quicktime"
                multiple
                type="file"
                onChange={handleFileChange}
              />
            </label>
            {files.length > 0 ? (
              <ul className="return-file-list">
                {files.map((file) => (
                  <li key={`${file.name}-${file.size}`}>
                    <span>{file.name}</span>
                    <button type="button" onClick={() => removeFile(file)}>
                      Убрать
                    </button>
                  </li>
                ))}
              </ul>
            ) : null}
          </section>

          {submitError ? <p className="form-error">{submitError}</p> : null}

          <button className="primary-button" disabled={submitting} type="submit">
            {submitting ? 'Отправляем...' : 'Отправить заявку'}
          </button>
        </form>
      ) : null}
    </div>
  );

  function toggleItem(orderItemId: number) {
    setSubmitError(null);
    setSelectedItems((current) => ({
      ...current,
      [orderItemId]: !current[orderItemId],
    }));
    setQuantities((current) => ({ ...current, [orderItemId]: current[orderItemId] ?? 1 }));
  }

  function updateQuantity(orderItemId: number, quantity: number) {
    setQuantities((current) => ({ ...current, [orderItemId]: quantity }));
  }

  function handleFileChange(event: React.ChangeEvent<HTMLInputElement>) {
    const selectedFiles = Array.from(event.target.files ?? []);
    event.target.value = '';
    setSubmitError(null);

    const nextFiles = [...files, ...selectedFiles];
    const validationError = validateFiles(nextFiles);
    if (validationError) {
      setSubmitError(validationError);
      return;
    }
    setFiles(nextFiles);
  }

  function removeFile(file: File) {
    setFiles((current) => current.filter((item) => item !== file));
  }

  async function submitReturnRequest(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!orderId) return;

    const items = eligibleItems
      .filter((item) => selectedItems[item.order_item_id])
      .map((item) => ({
        order_item_id: item.order_item_id,
        quantity: quantities[item.order_item_id] ?? 1,
      }));

    if (items.length === 0) {
      setSubmitError('Выберите хотя бы один товар.');
      return;
    }
    if (!reason.trim()) {
      setSubmitError('Укажите причину возврата.');
      return;
    }

    const validationError = validateFiles(files);
    if (validationError) {
      setSubmitError(validationError);
      return;
    }

    setSubmitting(true);
    setSubmitError(null);
    try {
      const result = await createReturnRequest(
        orderId,
        {
          reason: reason.trim(),
          comment: comment.trim() || null,
          items,
        },
        files,
      );
      setSuccessMessage(result.message ?? 'Заявка отправлена. Продавец свяжется с вами.');
    } catch (submitRequestError) {
      setSubmitError(toApiErrorMessage(submitRequestError));
    } finally {
      setSubmitting(false);
    }
  }
}

function ReturnItemCard({
  item,
  onQuantityChange,
  onToggle,
  quantity,
  selected,
}: {
  item: ReturnEligibilityItem;
  onQuantityChange: (quantity: number) => void;
  onToggle: () => void;
  quantity: number;
  selected: boolean;
}) {
  const imageUrl = normalizeAssetUrl(item.image_url);
  const meta = [item.color, item.size, item.sku ? `арт. ${item.sku}` : null]
    .filter(Boolean)
    .join(' · ');

  return (
    <article className={`return-item-card${selected ? ' return-item-card--selected' : ''}`}>
      <label className="return-item-card__check" aria-label="Выбрать товар">
        <input checked={selected} type="checkbox" onChange={onToggle} />
      </label>
      <span className="return-item-card__image">
        {imageUrl ? (
          <img src={imageUrl} alt="" width={64} height={80} loading="lazy" decoding="async" />
        ) : (
          item.product_name.slice(0, 1)
        )}
      </span>
      <div className="return-item-card__content">
        {item.product_brand ? <span>{item.product_brand}</span> : null}
        <strong>{item.product_name}</strong>
        {meta ? <p>{meta}</p> : null}
        <small>Куплено: {item.quantity}</small>
      </div>
      {item.quantity > 1 ? (
        <label className="return-item-card__quantity">
          <span>К возврату</span>
          <select
            disabled={!selected}
            value={quantity}
            onChange={(event) => onQuantityChange(Number(event.target.value))}
          >
            {Array.from({ length: item.quantity }, (_, index) => index + 1).map((value) => (
              <option value={value} key={value}>
                {value}
              </option>
            ))}
          </select>
        </label>
      ) : null}
    </article>
  );
}

function validateFiles(files: File[]) {
  if (files.length > MAX_RETURN_FILES) {
    return 'Можно прикрепить не больше 5 файлов.';
  }
  const invalidType = files.find((file) => !RETURN_FILE_TYPES.has(file.type));
  if (invalidType) {
    return 'Поддерживаются JPEG, PNG, WebP, MP4, WebM или MOV.';
  }
  const tooLarge = files.find((file) => file.size > MAX_RETURN_FILE_SIZE);
  if (tooLarge) {
    return 'Размер каждого файла не должен превышать 20 МБ.';
  }
  return null;
}
