import React from 'react';
import {
  getPendingPaymentSuccessBanner,
  markPaymentSuccessBannerSeen,
  type PaymentSuccessBannerPending,
} from '../../shared/api';
import { useAuth } from '../../shared/auth/AuthProvider';
import { useRouter } from '../../shared/router/RouterProvider';
import { normalizeAssetUrl } from '../../shared/utils/images';

const DISMISSED_STORAGE_KEY = 'stylexac.paymentSuccessBanner.dismissedOrderIds';

export function PaymentSuccessBannerController() {
  const { isAuthenticated } = useAuth();
  const { currentPath } = useRouter();
  const [pendingBanner, setPendingBanner] = React.useState<PaymentSuccessBannerPending | null>(
    null,
  );

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
    void markPaymentSuccessBannerSeen(orderId).catch(() => undefined);
  }, [pendingBanner]);

  if (!pendingBanner) {
    return null;
  }

  const imageUrl = normalizeAssetUrl(pendingBanner.image_url || pendingBanner.image_path);
  if (!imageUrl) {
    return null;
  }

  return (
    <button
      aria-label={`Покупка ${pendingBanner.order_number} завершена`}
      className="payment-success-banner-overlay"
      type="button"
      onClick={closeBanner}
    >
      <img
        alt=""
        className="payment-success-banner-overlay__image"
        src={imageUrl}
      />
    </button>
  );
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
