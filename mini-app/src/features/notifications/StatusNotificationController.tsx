import React from 'react';
import {
  getPendingCustomerInAppNotifications,
  markCustomerInAppNotificationSeen,
  type CustomerInAppNotification,
} from '../../shared/api';
import { useAuth } from '../../shared/auth/AuthProvider';
import { useRouter } from '../../shared/router/RouterProvider';
import { SellerContactCard } from '../../shared/ui';
import { formatPrice } from '../../shared/utils/format';
import { normalizeAssetUrl } from '../../shared/utils/images';

const POLL_INTERVAL_MS = 45_000;
const LEGACY_DISMISSED_STORAGE_KEY = 'stylexac.paymentSuccessBanner.dismissedOrderIds';

export function StatusNotificationController() {
  const { isAuthenticated } = useAuth();
  const { currentPath } = useRouter();
  const [queue, setQueue] = React.useState<CustomerInAppNotification[]>([]);
  const [acknowledging, setAcknowledging] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [contactsOpen, setContactsOpen] = React.useState(false);
  const inFlight = React.useRef(false);
  const previousFocus = React.useRef<HTMLElement | null>(null);
  const dialogRef = React.useRef<HTMLElement | null>(null);

  const refresh = React.useCallback(async () => {
    if (!isAuthenticated || inFlight.current) {
      if (!isAuthenticated) setQueue([]);
      return;
    }
    inFlight.current = true;
    try {
      const pending = await getPendingCustomerInAppNotifications({ retry: false });
      const legacyDismissed = pending.find(isLegacyDismissedLocally);
      if (legacyDismissed) {
        await markCustomerInAppNotificationSeen(legacyDismissed.id);
        const remaining = pending.filter((item) => item.id !== legacyDismissed.id);
        setQueue(remaining);
      } else {
        setQueue(pending);
      }
    } catch {
      // Durable server state will be retried on the next lifecycle refresh or poll.
    } finally {
      inFlight.current = false;
    }
  }, [isAuthenticated]);

  React.useEffect(() => {
    void refresh();
  }, [currentPath, refresh]);

  React.useEffect(() => {
    const onReturn = () => {
      if (document.visibilityState === 'visible') void refresh();
    };
    window.addEventListener('focus', onReturn);
    document.addEventListener('visibilitychange', onReturn);
    const interval = window.setInterval(() => {
      if (document.visibilityState === 'visible') void refresh();
    }, POLL_INTERVAL_MS);
    return () => {
      window.removeEventListener('focus', onReturn);
      document.removeEventListener('visibilitychange', onReturn);
      window.clearInterval(interval);
    };
  }, [refresh]);

  const current = queue[0] ?? null;
  React.useEffect(() => {
    if (!current) return;
    previousFocus.current = document.activeElement as HTMLElement | null;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    window.requestAnimationFrame(() => dialogRef.current?.focus());
    return () => {
      document.body.style.overflow = previousOverflow;
      previousFocus.current?.focus();
    };
  }, [current?.id]);

  React.useEffect(() => {
    setContactsOpen(false);
    setError(null);
  }, [current?.id]);

  const acknowledge = React.useCallback(async () => {
    if (!current || acknowledging) return;
    setAcknowledging(true);
    setError(null);
    try {
      await markCustomerInAppNotificationSeen(current.id);
      setQueue((items) => items.filter((item) => item.id !== current.id));
    } catch {
      setError('Не удалось подтвердить уведомление. Попробуйте ещё раз.');
    } finally {
      setAcknowledging(false);
    }
  }, [acknowledging, current]);

  if (!current) return null;
  const hasContacts = current.action_mode === 'continue_with_contacts';

  return (
    <div
      className={`status-notification-overlay status-notification-overlay--${current.variant}`}
      onMouseDown={(event) => event.stopPropagation()}
    >
      <section
        aria-describedby={current.variant === 'approved_payment' ? undefined : 'status-notification-message'}
        aria-labelledby="status-notification-title"
        aria-modal="true"
        className={`status-notification-card status-notification-card--${current.variant}`}
        onKeyDown={(event) => {
          if (event.key === 'Escape') event.preventDefault();
          if (event.key === 'Tab') keepFocusInDialog(event);
        }}
        ref={dialogRef}
        role="dialog"
        tabIndex={-1}
      >
        {current.variant === 'approved_payment' ? (
          <ApprovedPaymentContent notification={current} />
        ) : (
          <div className="status-notification-copy">
            <div aria-hidden="true" className="status-notification-symbol">✓</div>
            <h2 id="status-notification-title">{current.title}</h2>
            <p id="status-notification-message">{current.message}</p>
          </div>
        )}
        {error ? <p className="status-notification-error" role="alert">{error}</p> : null}
        <div className="status-notification-actions">
          {hasContacts ? (
            <button
              aria-expanded={contactsOpen}
              className="secondary-button"
              disabled={acknowledging}
              onClick={() => setContactsOpen((open) => !open)}
              type="button"
            >
              Связаться с продавцом
            </button>
          ) : null}
          <button
            className="primary-button"
            disabled={acknowledging}
            onClick={() => void acknowledge()}
            type="button"
          >
            {acknowledging ? 'Подтверждение…' : 'Продолжить'}
          </button>
        </div>
        {contactsOpen ? <SellerContactCard className="status-notification-contacts" /> : null}
      </section>
    </div>
  );
}

function ApprovedPaymentContent({ notification }: { notification: CustomerInAppNotification }) {
  const payload = notification.payload;
  const imageUrl = normalizeAssetUrl(payload.image_url || payload.image_path);
  const deliveryNote = payload.delivery_method === 'CDEK' || payload.delivery_method === 'WB';
  return (
    <>
      {imageUrl ? (
        <img
          alt=""
          className="status-notification-image status-notification-image--approved-payment"
          src={imageUrl}
        />
      ) : null}
      <div className="status-notification-payment-data">
        <h2 id="status-notification-title">{notification.title}</h2>
        <DataRow icon="◷" label="Дата покупки" value={formatDate(payload.order_created_at)} />
        <DataRow icon="✓" label="Платёж" value="Оплачено" success />
        <DataRow icon="₽" label="Сумма" value={formatPrice(payload.total_amount || '0')} />
        {deliveryNote ? (
          <p className="status-notification-delivery-note">
            Необходимо связаться с продавцом для оплаты доставки.
          </p>
        ) : null}
      </div>
    </>
  );
}

function DataRow({ icon, label, value, success = false }: {
  icon: string; label: string; value: string; success?: boolean;
}) {
  return (
    <div className="status-notification-data-row">
      <span aria-hidden="true" className="status-notification-data-row__icon">{icon}</span>
      <span><small>{label}</small><strong className={success ? 'is-success' : ''}>{value}</strong></span>
    </div>
  );
}

function formatDate(value?: string) {
  if (!value) return '—';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '—';
  return new Intl.DateTimeFormat('ru-RU', { day: '2-digit', month: 'long', year: 'numeric' })
    .format(date)
    .replace(/\s?г\.$/, '');
}

function isLegacyDismissedLocally(notification: CustomerInAppNotification) {
  if (!notification.payload.legacy || notification.order_id === null) return false;
  try {
    const parsed = JSON.parse(window.localStorage.getItem(LEGACY_DISMISSED_STORAGE_KEY) || '[]');
    return Array.isArray(parsed) && parsed.includes(notification.order_id);
  } catch {
    return false;
  }
}

function keepFocusInDialog(event: React.KeyboardEvent<HTMLElement>) {
  const focusable = Array.from(
    event.currentTarget.querySelectorAll<HTMLElement>(
      'button:not([disabled]), a[href], input:not([disabled]), [tabindex]:not([tabindex="-1"])',
    ),
  );
  if (focusable.length === 0) {
    event.preventDefault();
    event.currentTarget.focus();
    return;
  }
  const first = focusable[0];
  const last = focusable[focusable.length - 1];
  if (event.shiftKey && document.activeElement === first) {
    event.preventDefault();
    last.focus();
  } else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault();
    first.focus();
  }
}
