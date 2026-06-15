import React from 'react';
import {
  getOrderPayment,
  submitOrderPayment,
  toApiErrorMessage,
  uploadOrderPaymentReceipt,
  type ManualPayment,
  type ManualPaymentStatus,
} from '../shared/api';
import { useAuth } from '../shared/auth/AuthProvider';
import { getAuthPath, getNumericRouteParam, useRouter } from '../shared/router/RouterProvider';
import { EmptyState, ErrorState, InlineNotice, PageLoader, TopBar } from '../shared/ui';
import { formatPrice } from '../shared/utils/format';
import { normalizeAssetUrl } from '../shared/utils/images';

const ACTIVE_STATUSES: ManualPaymentStatus[] = ['PENDING', 'SUBMITTED'];
const MAX_RECEIPT_SIZE = 5 * 1024 * 1024;

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
  const [notice, setNotice] = React.useState<string | null>(null);
  const [busy, setBusy] = React.useState<'submit' | 'upload' | null>(null);
  const [clockOffsetMs, setClockOffsetMs] = React.useState(0);
  const [nowMs, setNowMs] = React.useState(Date.now());

  const loadPayment = React.useCallback(async (showLoader = false) => {
    if (!isAuthenticated || orderId === null) {
      setLoading(false);
      return null;
    }
    if (showLoader) setLoading(true);
    try {
      const result = await getOrderPayment(orderId);
      setPayment(result);
      setClockOffsetMs(new Date(result.server_now).getTime() - Date.now());
      setError(null);
      return result;
    } catch (loadError) {
      setError(toApiErrorMessage(loadError));
      return null;
    } finally {
      setLoading(false);
    }
  }, [isAuthenticated, orderId]);

  React.useEffect(() => {
    void loadPayment(true);
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
      setNotice(`${label} скопирован.`);
    } catch {
      setNotice('Не удалось скопировать. Нажмите и удерживайте значение.');
    }
  }

  async function submitPayment() {
    if (!payment || !canAct) return;
    setBusy('submit');
    setNotice(null);
    try {
      const result = await submitOrderPayment(payment.order_id);
      setPayment(result);
      setNotice('Оплата отправлена продавцу на проверку.');
    } catch (submitError) {
      const errorMessage = toApiErrorMessage(submitError);
      const refreshed = await loadPayment();
      setNotice(
        refreshed?.status === 'SUBMITTED'
          ? 'Оплата отправлена продавцу на проверку.'
          : errorMessage,
      );
    } finally {
      setBusy(null);
    }
  }

  async function uploadReceipt(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = '';
    if (!payment || !file || !canAct) return;
    if (!['image/jpeg', 'image/png', 'image/webp'].includes(file.type)) {
      setNotice('Загрузите изображение JPEG, PNG или WebP.');
      return;
    }
    if (file.size > MAX_RECEIPT_SIZE) {
      setNotice('Размер скриншота не должен превышать 5 МБ.');
      return;
    }

    setBusy('upload');
    setNotice(null);
    const previousReceiptPath = payment.receipt_image_path;
    try {
      const result = await uploadOrderPaymentReceipt(payment.order_id, file);
      setPayment(result);
      setNotice('Скриншот сохранен.');
    } catch (uploadError) {
      const errorMessage = toApiErrorMessage(uploadError);
      const refreshed = await loadPayment();
      setNotice(
        refreshed?.receipt_image_path
          && refreshed.receipt_image_path !== previousReceiptPath
          ? 'Скриншот сохранен.'
          : errorMessage,
      );
    } finally {
      setBusy(null);
    }
  }

  if (!isAuthenticated) {
    return (
      <div className="page payment-page">
        <TopBar title="Оплата заказа" onBack={() => navigate('/cart?tab=orders')} />
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
      <TopBar title="Оплата через СБП" onBack={() => navigate('/cart?tab=orders')} />
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
            <InlineNotice tone={notice.includes('сохранен') || notice.includes('скопирован') ? 'success' : 'info'}>
              <span>{notice}</span>
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
