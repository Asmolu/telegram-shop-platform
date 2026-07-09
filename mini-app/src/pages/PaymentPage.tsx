import React from 'react';
import {
  createIdempotencyKey,
  getApiErrorTelemetryCategory,
  getOrderPayment,
  isRequestAbortedError,
  isTemporaryNetworkError,
  submitOrderPayment,
  toApiErrorMessage,
  uploadOrderPaymentReceipt,
  type ManualPayment,
  type ManualPaymentStatus,
  type OrderDeliveryMethod,
} from '../shared/api';
import { useAuth } from '../shared/auth/AuthProvider';
import { useNetworkRetry } from '../shared/network/NetworkProvider';
import { getAuthPath, getNumericRouteParam, useRouter } from '../shared/router/RouterProvider';
import { hashCorrelationKey, trackTelemetry } from '../shared/telemetry';
import { EmptyState, ErrorState, InlineNotice, PageLoader, TopBar } from '../shared/ui';
import { runLockedAction } from '../shared/utils/actionLock';
import { formatPrice } from '../shared/utils/format';
import { normalizeAssetUrl } from '../shared/utils/images';
import { prepareReceiptImage } from '../shared/utils/receiptImage';

const ACTIVE_STATUSES: ManualPaymentStatus[] = ['PENDING', 'SUBMITTED'];
const MAX_RECEIPT_SIZE = 5 * 1024 * 1024;
type Notice = { message: string; tone: 'success' | 'info' | 'warning' | 'danger' };
type PreparedReceiptUpload = {
  file: File;
  idempotencyKey: string;
  originalName: string;
  signature: string;
};

const STATUS_LABELS: Record<ManualPaymentStatus, string> = {
  PENDING: 'Ожидает оплату',
  SUBMITTED: 'Оплата на проверке',
  APPROVED: 'Оплачено',
  REJECTED: 'Отклонено',
  EXPIRED: 'Истекло время оплаты',
  CANCELLED: 'Оплата отменена',
};

export function PaymentPage() {
  const { currentPath, pathname, navigate } = useRouter();
  const { isAuthenticated } = useAuth();
  const orderId = getNumericRouteParam(pathname, '/payment/');
  const [payment, setPayment] = React.useState<ManualPayment | null>(null);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);
  const [notice, setNotice] = React.useState<Notice | null>(null);
  const [busy, setBusy] = React.useState<'submit' | 'preparing' | 'upload' | null>(null);
  const [receiptRetry, setReceiptRetry] = React.useState<PreparedReceiptUpload | null>(null);
  const [clockOffsetMs, setClockOffsetMs] = React.useState(0);
  const [nowMs, setNowMs] = React.useState(Date.now());
  const loadControllerRef = React.useRef<AbortController | null>(null);
  const submitKeyRef = React.useRef<string | null>(null);
  const uploadActionRef = React.useRef<{ key: string; signature: string } | null>(null);
  const submitLockRef = React.useRef(false);
  const uploadLockRef = React.useRef(false);

  const loadPayment = React.useCallback(async (showLoader = false) => {
    if (!isAuthenticated || orderId === null) {
      setLoading(false);
      return null;
    }
    loadControllerRef.current?.abort();
    const controller = new AbortController();
    loadControllerRef.current = controller;
    if (showLoader) setLoading(true);
    try {
      const result = await getOrderPayment(orderId, {
        signal: controller.signal,
        dedupe: false,
      });
      setPayment(result);
      setClockOffsetMs(new Date(result.server_now).getTime() - Date.now());
      setError(null);
      return result;
    } catch (loadError) {
      if (isRequestAbortedError(loadError)) {
        return null;
      }
      setError(toApiErrorMessage(loadError));
      return null;
    } finally {
      if (loadControllerRef.current === controller) {
        loadControllerRef.current = null;
      }
      setLoading(false);
    }
  }, [isAuthenticated, orderId]);

  useNetworkRetry(() => void loadPayment(true));

  React.useEffect(() => {
    void loadPayment(true);
    return () => {
      loadControllerRef.current?.abort();
    };
  }, [loadPayment]);

  React.useEffect(() => {
    const timer = window.setInterval(() => setNowMs(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, []);

  React.useEffect(() => {
    if (!payment || !ACTIVE_STATUSES.includes(payment.status)) return undefined;
    const poller = window.setInterval(() => void loadPayment(), 10_000);
    return () => window.clearInterval(poller);
  }, [loadPayment, payment?.status]);

  const remainingSeconds = payment
    ? Math.max(0, Math.floor((new Date(payment.expires_at).getTime() - (nowMs + clockOffsetMs)) / 1000))
    : 0;
  const locallyExpired = Boolean(
    payment && ACTIVE_STATUSES.includes(payment.status) && remainingSeconds <= 0,
  );
  const canAct = Boolean(payment && ACTIVE_STATUSES.includes(payment.status) && !locallyExpired);

  async function copyValue(value: string, label: string) {
    try {
      await navigator.clipboard.writeText(value);
      setNotice({ message: `${label} скопирован.`, tone: 'success' });
    } catch {
      setNotice({
        message: 'Не удалось скопировать. Нажмите и удерживайте значение.',
        tone: 'warning',
      });
    }
  }

  async function submitPayment() {
    await runLockedAction(submitLockRef, async () => {
      if (!payment || !canAct) return;
      setBusy('submit');
      setNotice(null);
      try {
        if (!submitKeyRef.current) {
          submitKeyRef.current = createIdempotencyKey('payment-submit');
        }
        const submitKey = submitKeyRef.current;
        trackTelemetry('payment.submit_started', {
          route: '/payment/:id',
          endpoint_scope: '/orders/:id/payment/submit',
          method: 'POST',
        }, { priority: 'critical' });
        const result = await submitOrderPayment(payment.order_id, submitKey);
        const refreshed = await loadPayment();
        setPayment(refreshed ?? result);
        submitKeyRef.current = null;
        trackTelemetry('payment.submit_completed', {
          route: '/payment/:id',
          endpoint_scope: '/orders/:id/payment/submit',
          method: 'POST',
          success: true,
          idempotency_key_hash: await hashCorrelationKey(submitKey),
        }, { priority: 'critical' });
        setNotice({
          message: 'Оплата отправлена продавцу на проверку.',
          tone: 'success',
        });
      } catch (submitError) {
        const submitHash = submitKeyRef.current
          ? await hashCorrelationKey(submitKeyRef.current)
          : undefined;
        trackTelemetry('payment.submit_failed', {
          route: '/payment/:id',
          endpoint_scope: '/orders/:id/payment/submit',
          method: 'POST',
          error_category: getApiErrorTelemetryCategory(submitError),
          success: false,
          idempotency_key_hash: submitHash,
        }, { priority: 'critical' });
        if (!isTemporaryNetworkError(submitError)) {
          submitKeyRef.current = null;
        }
        const errorMessage = toApiErrorMessage(submitError);
        const refreshed = await loadPayment();
        setNotice(refreshed?.status === 'SUBMITTED'
          ? { message: 'Оплата отправлена продавцу на проверку.', tone: 'success' }
          : { message: errorMessage, tone: 'danger' });
      } finally {
        setBusy(null);
      }
    });
  }

  async function uploadReceipt(event: React.ChangeEvent<HTMLInputElement>) {
    const selectedFile = event.target.files?.[0];
    event.target.value = '';
    await runLockedAction(uploadLockRef, async () => {
      if (!payment || !selectedFile || !canAct) return;
      const file = selectedFile;
      if (!['image/jpeg', 'image/png', 'image/webp'].includes(file.type)) {
        setNotice({
          message: 'Загрузите изображение JPEG, PNG или WebP.',
          tone: 'warning',
        });
        return;
      }
      setBusy('preparing');
      setNotice(null);
      const uploadSignature = getReceiptFileSignature(file);
      if (uploadActionRef.current?.signature !== uploadSignature) {
        uploadActionRef.current = {
          key: createIdempotencyKey('receipt-upload'),
          signature: uploadSignature,
        };
      }
      const uploadAction = uploadActionRef.current!;
      const prepareStartedAt = Date.now();
      const prepared = await prepareReceiptImage(file);
      trackTelemetry('receipt.prepare_completed', {
        route: '/payment/:id',
        duration_ms: Date.now() - prepareStartedAt,
        payload_size_bucket: byteBucket(prepared.file.size),
        success: true,
      });
      if (prepared.file.size > MAX_RECEIPT_SIZE) {
        uploadActionRef.current = null;
        setBusy(null);
        setNotice({
          message: 'Размер скриншота не должен превышать 5 МБ.',
          tone: 'warning',
        });
        return;
      }

      setBusy('upload');
      const previousReceiptPath = payment.receipt_image_path;
      try {
        const uploadStartedAt = Date.now();
        const result = await uploadOrderPaymentReceipt(
          payment.order_id,
          prepared.file,
          uploadAction.key,
        );
        if (!result.receipt_image_path || !result.receipt_image_url) {
          throw new Error('Сервер не подтвердил сохранение скриншота.');
        }
        const refreshed = await loadPayment();
        if (
          !refreshed?.receipt_image_path
          || !refreshed.receipt_image_url
          || refreshed.receipt_image_path !== result.receipt_image_path
        ) {
          throw new Error('Не удалось подтвердить сохранение скриншота.');
        }
        setPayment(refreshed);
        uploadActionRef.current = null;
        setReceiptRetry(null);
        trackTelemetry('receipt.upload_completed', {
          route: '/payment/:id',
          endpoint_scope: '/orders/:id/payment/receipt',
          method: 'POST',
          duration_ms: Date.now() - uploadStartedAt,
          payload_size_bucket: byteBucket(prepared.file.size),
          success: true,
          idempotency_key_hash: await hashCorrelationKey(uploadAction.key),
        }, { priority: 'critical' });
        setNotice({ message: 'Скриншот сохранен.', tone: 'success' });
      } catch (uploadError) {
        trackTelemetry('receipt.upload_failed', {
          route: '/payment/:id',
          endpoint_scope: '/orders/:id/payment/receipt',
          method: 'POST',
          payload_size_bucket: byteBucket(prepared.file.size),
          error_category: getApiErrorTelemetryCategory(uploadError),
          success: false,
          idempotency_key_hash: await hashCorrelationKey(uploadAction.key),
        }, { priority: 'critical' });
        if (isTemporaryNetworkError(uploadError)) {
          setReceiptRetry({
            file: prepared.file,
            idempotencyKey: uploadAction.key,
            originalName: file.name,
            signature: uploadSignature,
          });
        } else {
          uploadActionRef.current = null;
          setReceiptRetry(null);
        }
        const errorMessage = toApiErrorMessage(uploadError);
        const refreshed = await loadPayment();
        const recovered = Boolean(
          refreshed?.receipt_image_path
          && refreshed.receipt_image_url
          && refreshed.receipt_image_path !== previousReceiptPath,
        );
        setNotice(recovered
          ? { message: 'Скриншот сохранен.', tone: 'success' }
          : { message: errorMessage, tone: 'danger' });
      } finally {
        setBusy(null);
      }
    });
  }

  async function retryReceiptUpload() {
    await runLockedAction(uploadLockRef, async () => {
      if (!payment || !receiptRetry || !canAct) return;
      setBusy('upload');
      setNotice(null);
      const previousReceiptPath = payment.receipt_image_path;
      try {
        const uploadStartedAt = Date.now();
        const result = await uploadOrderPaymentReceipt(
          payment.order_id,
          receiptRetry.file,
          receiptRetry.idempotencyKey,
        );
        if (!result.receipt_image_path || !result.receipt_image_url) {
          throw new Error('Сервер не подтвердил сохранение скриншота.');
        }
        const refreshed = await loadPayment();
        if (
          !refreshed?.receipt_image_path
          || !refreshed.receipt_image_url
          || refreshed.receipt_image_path !== result.receipt_image_path
        ) {
          throw new Error('Не удалось подтвердить сохранение скриншота.');
        }
        setPayment(refreshed);
        uploadActionRef.current = null;
        setReceiptRetry(null);
        trackTelemetry('receipt.upload_completed', {
          route: '/payment/:id',
          endpoint_scope: '/orders/:id/payment/receipt',
          method: 'POST',
          duration_ms: Date.now() - uploadStartedAt,
          payload_size_bucket: byteBucket(receiptRetry.file.size),
          success: true,
          idempotency_key_hash: await hashCorrelationKey(receiptRetry.idempotencyKey),
        }, { priority: 'critical' });
        setNotice({ message: 'Скриншот сохранен.', tone: 'success' });
      } catch (uploadError) {
        trackTelemetry('receipt.upload_failed', {
          route: '/payment/:id',
          endpoint_scope: '/orders/:id/payment/receipt',
          method: 'POST',
          payload_size_bucket: byteBucket(receiptRetry.file.size),
          error_category: getApiErrorTelemetryCategory(uploadError),
          success: false,
          idempotency_key_hash: await hashCorrelationKey(receiptRetry.idempotencyKey),
        }, { priority: 'critical' });
        if (!isTemporaryNetworkError(uploadError)) {
          uploadActionRef.current = null;
          setReceiptRetry(null);
        }
        const errorMessage = toApiErrorMessage(uploadError);
        const refreshed = await loadPayment();
        const recovered = Boolean(
          refreshed?.receipt_image_path
          && refreshed.receipt_image_url
          && refreshed.receipt_image_path !== previousReceiptPath,
        );
        setNotice(recovered
          ? { message: 'Скриншот сохранен.', tone: 'success' }
          : { message: errorMessage, tone: 'danger' });
      } finally {
        setBusy(null);
      }
    });
  }

  if (!isAuthenticated) {
    return (
      <div className="page payment-page">
        <TopBar title="Оплата заказа" backFallback="/cart?tab=orders" />
        <EmptyState
          title="Нужен вход через Telegram"
          actionLabel="Войти"
          onAction={() => navigate(getAuthPath(currentPath))}
        />
      </div>
    );
  }

  return (
    <div className="page payment-page">
      <TopBar title="Оплата через СБП" backFallback="/cart?tab=orders" />
      {loading ? <PageLoader text="Загружаем реквизиты..." /> : null}
      {!loading && error ? (
        <ErrorState
          message={error}
          actionLabel="Повторить"
          onAction={() => void loadPayment(true)}
        />
      ) : null}
      {!loading && !error && payment ? (
        <>
          {notice ? (
            <InlineNotice tone={notice.tone}>
              <span>{notice.message}</span>
              <button type="button" onClick={() => setNotice(null)}>×</button>
            </InlineNotice>
          ) : null}

          <section className={`payment-status-card payment-status-card--${payment.status.toLowerCase()}`}>
            <span>{STATUS_LABELS[payment.status]}</span>
            <strong>Заказ {payment.order_number}</strong>
            {ACTIVE_STATUSES.includes(payment.status) ? (
              <div className="payment-countdown">
                <small>Резерв товара</small>
                <strong>{locallyExpired ? '00:00' : formatCountdown(remainingSeconds)}</strong>
              </div>
            ) : null}
          </section>

          {payment.status === 'PENDING' ? (
            <section className="payment-help-card">
              <p>Переведите полную сумму через СБП по номеру телефона продавца.</p>
              <p>После перевода нажмите «Я оплатил».</p>
              <p>Продавец проверит поступление вручную.</p>
            </section>
          ) : null}

          <section className="payment-details-card">
            <PaymentRow
              label="Сумма"
              value={formatPrice(payment.amount)}
              onCopy={() => copyValue(payment.amount, 'Сумма')}
            />
            {payment.delivery_method ? (
              <PaymentRow
                label="Способ доставки"
                value={deliveryMethodLabel(payment.delivery_method)}
              />
            ) : null}
            <PaymentRow
              label="Телефон продавца"
              value={payment.seller_phone_display}
              onCopy={() => copyValue(payment.seller_phone_e164, 'Телефон')}
            />
            {payment.seller_bank_name ? (
              <PaymentRow
                label="Банк"
                value={payment.seller_bank_name}
                onCopy={() => copyValue(payment.seller_bank_name ?? '', 'Банк')}
              />
            ) : null}
            {payment.seller_recipient_name ? (
              <PaymentRow
                label="Получатель"
                value={payment.seller_recipient_name}
                onCopy={() => copyValue(payment.seller_recipient_name ?? '', 'Получатель')}
              />
            ) : null}
            <PaymentRow
              label="Комментарий к переводу"
              value={payment.payment_comment}
              onCopy={() => copyValue(payment.payment_comment, 'Комментарий')}
            />
          </section>

          {payment.receipt_image_url ? (
            <section className="payment-receipt-card">
              <span>Скриншот перевода</span>
              <img
                src={normalizeAssetUrl(payment.receipt_image_url) ?? undefined}
                alt="Скриншот перевода"
              />
            </section>
          ) : null}

          {payment.status === 'SUBMITTED' ? (
            <InlineNotice tone="info">
              Оплата отправлена на проверку. Продавец подтвердит поступление вручную.
            </InlineNotice>
          ) : null}
          {payment.status === 'REJECTED' ? (
            <InlineNotice tone="danger">
              {payment.reject_reason || 'Продавец не подтвердил поступление денег.'} Резерв товара снят.
            </InlineNotice>
          ) : null}
          {payment.status === 'EXPIRED' || locallyExpired ? (
            <InlineNotice tone="warning">
              Время оплаты истекло. Заказ отменен, резерв товара снят.
            </InlineNotice>
          ) : null}
          {payment.status === 'APPROVED' ? (
            <InlineNotice tone="success">Оплата подтверждена. Заказ принят в обработку.</InlineNotice>
          ) : null}

          {canAct ? (
            <div className="payment-actions">
              <label className="secondary-button payment-upload-button">
                {busy === 'upload' ? 'Загружаем...' : payment.receipt_image_path ? 'Заменить скриншот' : 'Загрузить скриншот'}
                <input
                  accept="image/jpeg,image/png,image/webp"
                  disabled={busy !== null}
                  type="file"
                  onChange={uploadReceipt}
                />
              </label>
              {busy === 'preparing' ? (
                <span className="payment-upload-status">Готовим скриншот...</span>
              ) : null}
              {receiptRetry ? (
                <button
                  className="secondary-button"
                  disabled={busy !== null}
                  type="button"
                  onClick={() => void retryReceiptUpload()}
                >
                  {busy === 'upload' ? 'Повторяем...' : 'Повторить загрузку'}
                </button>
              ) : null}
              <button
                className="primary-button"
                disabled={busy !== null || payment.status === 'SUBMITTED'}
                type="button"
                onClick={submitPayment}
              >
                {payment.status === 'SUBMITTED' ? 'На проверке' : busy === 'submit' ? 'Отправляем...' : 'Я оплатил'}
              </button>
            </div>
          ) : null}

          <button className="text-button payment-orders-link" type="button" onClick={() => navigate('/cart?tab=orders')}>
            Перейти к моим заказам
          </button>
        </>
      ) : null}
    </div>
  );
}

function getReceiptFileSignature(file: File) {
  return `${file.name}:${file.type}:${file.size}:${file.lastModified}`;
}

function PaymentRow({
  label,
  value,
  onCopy,
}: {
  label: string;
  value: string;
  onCopy?: () => void;
}) {
  return (
    <div className="payment-details-row">
      <span>{label}</span>
      <strong>{value}</strong>
      {onCopy ? <button type="button" onClick={onCopy}>Копировать</button> : null}
    </div>
  );
}

function formatCountdown(totalSeconds: number) {
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;
}

function byteBucket(bytes: number): '0' | '1kb' | '10kb' | '100kb' | '1mb' | 'large' {
  if (bytes <= 0) {
    return '0';
  }
  if (bytes <= 1024) {
    return '1kb';
  }
  if (bytes <= 10 * 1024) {
    return '10kb';
  }
  if (bytes <= 100 * 1024) {
    return '100kb';
  }
  if (bytes <= 1024 * 1024) {
    return '1mb';
  }
  return 'large';
}

function deliveryMethodLabel(method: OrderDeliveryMethod): string {
  return {
    ROUTE_TAXI: 'Маршруткой',
    CITY_DELIVERY: 'Доставка по городу',
    OZON: 'Озон доставка',
    WB: 'ВБ доставка',
    CDEK: 'СДЭК',
    PICKUP: 'Самовывоз',
  }[method];
}
