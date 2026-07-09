import React from 'react';
import {
  getPendingPaymentSuccessBanner,
  markPaymentSuccessBannerSeen,
  type PaymentSuccessBannerPending,
} from '../../shared/api';
import { useAuth } from '../../shared/auth/AuthProvider';
import { useRouter } from '../../shared/router/RouterProvider';
import { SellerContactCard } from '../../shared/ui';
import { formatPrice } from '../../shared/utils/format';
import { normalizeAssetUrl } from '../../shared/utils/images';

const DISMISSED_STORAGE_KEY = 'stylexac.paymentSuccessBanner.dismissedOrderIds';

export function PaymentSuccessBannerController() {
  const { isAuthenticated } = useAuth();
  const { currentPath } = useRouter();
  const [pendingBanner, setPendingBanner] = React.useState<PaymentSuccessBannerPending | null>(
    null,
  );
  const [contactsOpen, setContactsOpen] = React.useState(false);

  const fetchPendingBanner = React.useCallback(async () => {
    if (!isAuthenticated) {
      setPendingBanner(null);
      return;
    }

    try {
      const banner = await getPendingPaymentSuccessBanner({ retry: false });
      if (banner && !isOrderDismissedLocally(banner.order_id)) {
        setPendingBanner(banner);
      } else {
        setPendingBanner(null);
      }
    } catch {
      setPendingBanner(null);
    }
  }, [isAuthenticated]);

  React.useEffect(() => {
    void fetchPendingBanner();
  }, [currentPath, fetchPendingBanner]);

  React.useEffect(() => {
    const handleAppReturn = () => {
      if (document.visibilityState !== 'hidden') {
        void fetchPendingBanner();
      }
    };

    window.addEventListener('focus', handleAppReturn);
    document.addEventListener('visibilitychange', handleAppReturn);
    return () => {
      window.removeEventListener('focus', handleAppReturn);
      document.removeEventListener('visibilitychange', handleAppReturn);
    };
  }, [fetchPendingBanner]);

  const closeBanner = React.useCallback(() => {
    if (!pendingBanner) {
      return;
    }

    const orderId = pendingBanner.order_id;
    rememberOrderDismissedLocally(orderId);
    setPendingBanner(null);
    setContactsOpen(false);
    void markPaymentSuccessBannerSeen(orderId).catch(() => undefined);
  }, [pendingBanner]);

  if (!pendingBanner) {
    return null;
  }

  const imageUrl = normalizeAssetUrl(pendingBanner.image_url || pendingBanner.image_path);
  if (!imageUrl) {
    return null;
  }

  const showDeliveryNote = pendingBanner.delivery_method === 'CDEK' || pendingBanner.delivery_method === 'WB';

  return (
    <div
      aria-label={`Покупка ${pendingBanner.order_number} завершена`}
      className="payment-success-banner-overlay"
      role="button"
      tabIndex={0}
      onClick={closeBanner}
      onKeyDown={(event) => {
        if (event.key === 'Escape' || event.key === 'Enter' || event.key === ' ') {
          event.preventDefault();
          closeBanner();
        }
      }}
    >
      <section
        className="payment-success-banner-card"
        onClick={(event) => event.stopPropagation()}
        onKeyDown={(event) => event.stopPropagation()}
      >
        <img
          alt=""
          className="payment-success-banner-overlay__image"
          src={imageUrl}
        />
        <div className="payment-success-banner-data">
          <strong>Заказ {pendingBanner.order_number}</strong>
          <span>Дата покупки: {formatPaidBannerDate(pendingBanner.created_at)}</span>
          <span>Платёж: Оплачено</span>
          <span>Сумма: {formatPrice(pendingBanner.total_amount)}</span>
          {showDeliveryNote ? (
            <p>Необходимо связаться с продавцом для оплаты доставки.</p>
          ) : null}
          <div className="payment-success-banner-actions">
            <button
              className="secondary-button"
              type="button"
              aria-expanded={contactsOpen}
              onClick={() => setContactsOpen((current) => !current)}
            >
              Связаться с продавцом
            </button>
            <button className="primary-button" type="button" onClick={closeBanner}>
              Продолжить
            </button>
          </div>
          {contactsOpen ? <SellerContactCard className="payment-success-banner-contacts" /> : null}
        </div>
      </section>
    </div>
  );
}

function formatPaidBannerDate(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return '—';
  }
  return new Intl.DateTimeFormat('ru-RU', {
    day: '2-digit',
    month: 'long',
    year: 'numeric',
  }).format(date).replace(/\s?г\.$/, '');
}

function isOrderDismissedLocally(orderId: number) {
  return readDismissedOrderIds().has(orderId);
}

function rememberOrderDismissedLocally(orderId: number) {
  const orderIds = readDismissedOrderIds();
  orderIds.add(orderId);
  try {
    window.localStorage.setItem(
      DISMISSED_STORAGE_KEY,
      JSON.stringify([...orderIds].slice(-50)),
    );
  } catch {
    // Embedded browsers can deny localStorage; the server seen mark still handles persistence.
  }
}

function readDismissedOrderIds() {
  try {
    const rawValue = window.localStorage.getItem(DISMISSED_STORAGE_KEY);
    if (!rawValue) {
      return new Set<number>();
    }
    const values = JSON.parse(rawValue);
    if (!Array.isArray(values)) {
      return new Set<number>();
    }
    return new Set(values.filter((value): value is number => Number.isInteger(value)));
  } catch {
    return new Set<number>();
  }
}
