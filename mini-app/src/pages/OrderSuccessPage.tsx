import React from 'react';
import { getOrder, toApiErrorMessage, type Order } from '../shared/api';
import { useAuth } from '../shared/auth/AuthProvider';
import { getAuthPath, getNumericRouteParam, getSafeReturnTo, Link, useRouter, withReturnTo } from '../shared/router/RouterProvider';
import { EmptyState, ErrorState, PageLoader, TopBar } from '../shared/ui';
import { formatDate, formatOrderStatus, formatPrice } from '../shared/utils/format';
import { normalizeAssetUrl } from '../shared/utils/images';
import { displaySize } from '../shared/utils/sizes';

const DELIVERY_METHOD_LABELS: Record<string, string> = {
  ROUTE_TAXI: 'Маршруткой',
  CITY_DELIVERY: 'Доставка по городу',
  OZON: 'Ozon доставка',
  WB: 'WB доставка',
  CDEK: 'СДЭК',
};

function formatDeliveryMethod(method: Order['delivery_method']) {
  return method ? DELIVERY_METHOD_LABELS[method] ?? method : 'Не указан';
}

function formatPaymentStatus(status: NonNullable<Order['manual_payment']>['status'] | null | undefined) {
  if (!status) {
    return 'Не указан';
  }

  const labels = {
    PENDING: 'Ожидает оплату',
    SUBMITTED: 'Оплата на проверке',
    APPROVED: 'Оплачено',
    REJECTED: 'Отклонено',
    EXPIRED: 'Время оплаты истекло',
    CANCELLED: 'Отменено',
  };
  return labels[status];
}

function getDeliveryCommentLines(comment: string | null | undefined) {
  return (comment ?? '')
    .split('\n')
    .map((line) => line.trim())
    .filter(Boolean);
}

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
        <OrderDetailContent
          currentPath={currentPath}
          order={order}
          onBackToShopping={() => navigate(returnTo)}
          onOpenOrders={() => navigate('/cart?tab=orders')}
        />
      ) : null}
    </div>
  );
}

function OrderDetailContent({
  currentPath,
  order,
  onBackToShopping,
  onOpenOrders,
}: {
  currentPath: string;
  order: Order;
  onBackToShopping: () => void;
  onOpenOrders: () => void;
}) {
  const promoCode = order.promo_code_code ?? order.promo_code;
  const discountAmount = Number(order.discount_amount ?? order.discount ?? 0);
  const paymentStatus = order.manual_payment?.status ?? null;
  const deliveryCommentLines = getDeliveryCommentLines(order.delivery_comment);

  return (
    <div className="order-detail">
      <section className="success-card order-detail-hero">
        <div className="success-icon">✓</div>
        <h1>Заказ создан</h1>
        <p>Заказ {order.order_number}</p>
        <strong>{formatPrice(order.total_amount)}</strong>
        <span className={`status-pill status-pill--${order.status.toLowerCase()}`}>
          {formatOrderStatus(order.status)}
        </span>
        <div className="button-row">
          <button className="primary-button" type="button" onClick={onOpenOrders}>
            Перейти к заказам
          </button>
          <button className="secondary-button" type="button" onClick={onBackToShopping}>
            Вернуться к покупкам
          </button>
        </div>
      </section>

      <section className="order-detail-section">
        <h2>Сводка</h2>
        <dl className="order-detail-list">
          <div><dt>Номер</dt><dd>{order.order_number}</dd></div>
          <div><dt>Создан</dt><dd>{formatDate(order.created_at)}</dd></div>
          <div><dt>Статус заказа</dt><dd>{formatOrderStatus(order.status)}</dd></div>
          <div><dt>Статус оплаты</dt><dd>{formatPaymentStatus(paymentStatus)}</dd></div>
          <div><dt>Доставка</dt><dd>{formatDeliveryMethod(order.delivery_method)}</dd></div>
          <div><dt>Итого</dt><dd>{formatPrice(order.total_amount)}</dd></div>
        </dl>
      </section>

      <section className="order-detail-section">
        <h2>Товары</h2>
        <div className="order-detail-items">
          {order.items.map((item) => (
            <OrderDetailItem item={item} currentPath={currentPath} key={item.id} />
          ))}
        </div>
      </section>

      <section className="order-detail-section">
        <h2>Оплата и сумма</h2>
        <dl className="order-detail-list">
          <div><dt>Товары</dt><dd>{formatPrice(order.subtotal_amount ?? order.subtotal)}</dd></div>
          {discountAmount > 0 ? (
            <div><dt>{promoCode ? `Промокод ${promoCode}` : 'Скидка'}</dt><dd>−{formatPrice(discountAmount)}</dd></div>
          ) : (
            <div><dt>Скидка</dt><dd>{formatPrice(0)}</dd></div>
          )}
          <div><dt>Статус оплаты</dt><dd>{formatPaymentStatus(paymentStatus)}</dd></div>
          <div className="order-detail-list__total"><dt>Итого</dt><dd>{formatPrice(order.total_amount ?? order.total)}</dd></div>
        </dl>
      </section>

      <section className="order-detail-section">
        <h2>Получатель и доставка</h2>
        <dl className="order-detail-list">
          <div><dt>Получатель</dt><dd>{order.contact_name}</dd></div>
          <div><dt>Телефон</dt><dd>{order.contact_phone}</dd></div>
          <div><dt>Город</dt><dd>{order.delivery_address}</dd></div>
          <div><dt>Способ</dt><dd>{formatDeliveryMethod(order.delivery_method)}</dd></div>
          {deliveryCommentLines.length > 0 ? (
            <div><dt>Комментарий</dt><dd>{deliveryCommentLines.join(' · ')}</dd></div>
          ) : null}
        </dl>
      </section>
    </div>
  );
}

function OrderDetailItem({
  currentPath,
  item,
}: {
  currentPath: string;
  item: Order['items'][number];
}) {
  const thumbnailUrl = normalizeAssetUrl(item.product_thumbnail_url || item.product_thumbnail_path);
  const productPath = withReturnTo(`/product/${item.product_id}`, currentPath);
  const brand = item.product_brand?.trim();
  const color = item.variant_color?.trim();
  const size = displaySize(item.variant_size_grid, item.variant_size, true);
  const sku = item.variant_sku?.trim();

  return (
    <article className="order-detail-item">
      <Link className="order-detail-item__image" to={productPath}>
        {thumbnailUrl ? (
          <img src={thumbnailUrl} alt="" width={72} height={90} loading="lazy" decoding="async" />
        ) : (
          <span>{item.product_name.slice(0, 1)}</span>
        )}
      </Link>
      <div className="order-detail-item__content">
        {brand ? <span>{brand}</span> : null}
        <Link to={productPath}>{item.product_title ?? item.product_name}</Link>
        <dl>
          {color ? <div><dt>Цвет</dt><dd>{color}</dd></div> : null}
          <div><dt>Размер</dt><dd>{size}</dd></div>
          {sku ? <div><dt>Артикул</dt><dd>{sku}</dd></div> : null}
          <div><dt>Кол-во</dt><dd>{item.quantity}</dd></div>
        </dl>
      </div>
      <div className="order-detail-item__price">
        <strong>{formatPrice(item.unit_price)}</strong>
        <span>{formatPrice(item.item_total ?? item.subtotal)}</span>
      </div>
    </article>
  );
}
