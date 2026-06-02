import React from 'react';
import { getOrder, toApiErrorMessage, type Order } from '../shared/api';
import { useAuth } from '../shared/auth/AuthProvider';
import { getAuthPath, getNumericRouteParam, getSafeReturnTo, useRouter } from '../shared/router/RouterProvider';
import { EmptyState, ErrorState, PageLoader, TopBar } from '../shared/ui';
import { formatOrderStatus, formatPrice } from '../shared/utils/format';

export function OrderSuccessPage() {
  const { currentPath, pathname, searchParams, navigate } = useRouter();
  const { isAuthenticated } = useAuth();
  const orderId = getNumericRouteParam(pathname, '/order-success/');
  const returnTo = getSafeReturnTo(searchParams.get('returnTo'));
  const [order, setOrder] = React.useState<Order | null>(null);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);

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
        const result = await getOrder(orderId);
        if (!cancelled) setOrder(result);
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

  if (!isAuthenticated) {
    return (
      <div className="page">
        <TopBar title="Заказ" />
        <EmptyState
          title="Нужен вход через Telegram"
          message="Детали заказа доступны после входа."
          actionLabel="Войти"
          onAction={() => navigate(getAuthPath(currentPath))}
        />
      </div>
    );
  }

  return (
    <div className="page">
      <TopBar title="Заказ" />
      {loading ? <PageLoader text="Загружаем заказ..." /> : null}
      {!loading && error ? <ErrorState message={error} /> : null}
      {!loading && !error && order ? (
        <section className="success-card">
          <div className="success-icon">✓</div>
          <h1>Заказ создан</h1>
          <p>Заказ {order.order_number}</p>
          <strong>{formatPrice(order.total_amount)}</strong>
          <span className={`status-pill status-pill--${order.status.toLowerCase()}`}>
            {formatOrderStatus(order.status)}
          </span>
          <div className="button-row">
            <button className="primary-button" type="button" onClick={() => navigate('/cart?tab=orders')}>
              Перейти к заказам
            </button>
            <button className="secondary-button" type="button" onClick={() => navigate(returnTo)}>
              Вернуться к покупкам
            </button>
          </div>
        </section>
      ) : null}
    </div>
  );
}
