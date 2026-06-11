import { FormEvent, useEffect, useState } from 'react';
import { api, resolveMediaUrl } from '../../shared/api';
import type { Order, OrderStatus, ProductSizeGrid } from '../../shared/api';
import { labelForEnum, useI18n } from '../../shared/i18n';
import { ErrorState, LoadingState } from '../../shared/ui/DataState';
import { StatusBadge } from '../../shared/ui/StatusBadge';
import { compactText, formatDate, formatMoney } from '../../shared/utils/format';

interface PageProps {
  onNavigate: (path: string) => void;
  onAuthExpired: () => void;
}

interface OrderFilters {
  search: string;
  status: '' | OrderStatus;
}

const initialFilters: OrderFilters = { search: '', status: '' };
const orderStatuses: OrderStatus[] = ['NEW', 'PROCESSING', 'SHIPPED', 'DELIVERED', 'CANCELLED'];

export function OrdersPage({ onNavigate, onAuthExpired }: PageProps) {
  const { language, t } = useI18n();
  const [orders, setOrders] = useState<Order[]>([]);
  const [selectedOrder, setSelectedOrder] = useState<Order | null>(null);
  const [selectedOrderLoading, setSelectedOrderLoading] = useState(false);
  const [filters, setFilters] = useState<OrderFilters>(initialFilters);
  const [draftFilters, setDraftFilters] = useState<OrderFilters>(initialFilters);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<unknown>(null);
  const [notice, setNotice] = useState<string | null>(null);

  function loadOrders() {
    setLoading(true);
    setError(null);

    api.orders
      .listAdmin({
        limit: 100,
        offset: 0,
        search: filters.search,
        status: filters.status,
      })
      .then((orderList) => setOrders(orderList.items))
      .catch(setError)
      .finally(() => setLoading(false));
  }

  useEffect(() => {
    loadOrders();
  }, [filters]);

  function applyFilters(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setFilters(draftFilters);
  }

  async function updateOrderStatus(order: Order, status: OrderStatus) {
    if (status === 'CANCELLED' && !window.confirm(t('orders.cancelConfirm'))) {
      return;
    }

    setNotice(null);
    try {
      const updated = await api.orders.updateStatus(order.id, status);
      setOrders((current) => current.map((item) => (item.id === updated.id ? updated : item)));
      setSelectedOrder((current) => (current?.id === updated.id ? updated : current));
      setNotice(t('orders.updated', { orderNumber: updated.order_number }));
    } catch (requestError) {
      setError(requestError);
    }
  }

  function selectOrderDetails(order: Order) {
    setSelectedOrder(order);
    setSelectedOrderLoading(true);
    api.orders
      .getAdmin(order.id)
      .then(setSelectedOrder)
      .catch(setError)
      .finally(() => setSelectedOrderLoading(false));
  }

  if (loading) return <LoadingState title={t('orders.loading')} />;
  if (error) {
    return <ErrorState error={error} onRetry={loadOrders} onAuthExpired={onAuthExpired} />;
  }

  return (
    <div className="page-stack">
      <div className="page-toolbar">
        <form className="filters-row" onSubmit={applyFilters}>
          <label>
            <span>{t('common.search')}</span>
            <input
              value={draftFilters.search}
              onChange={(event) =>
                setDraftFilters((current) => ({ ...current, search: event.target.value }))
              }
              placeholder={t('orders.searchPlaceholder')}
            />
          </label>
          <label>
            <span>{t('common.status')}</span>
            <select
              value={draftFilters.status}
              onChange={(event) =>
                setDraftFilters((current) => ({
                  ...current,
                  status: event.target.value as OrderFilters['status'],
                }))
              }
            >
              <option value="">{t('common.allStatuses')}</option>
              {orderStatuses.map((status) => (
                <option key={status} value={status}>
                  {labelForEnum(status, t)}
                </option>
              ))}
            </select>
          </label>
          <button className="button button-secondary" type="submit">
            {t('common.apply')}
          </button>
        </form>
      </div>

      {notice ? <div className="success-banner">{notice}</div> : null}

      <div className="split-view">
        <div className="table-panel">
          <table>
            <thead>
              <tr>
                <th>{t('orders.order')}</th>
                <th>{t('orders.customer')}</th>
                <th>{t('orders.contact')}</th>
                <th>{t('common.total')}</th>
                <th>{t('orders.promo')}</th>
                <th>{t('common.status')}</th>
                <th>{t('common.date')}</th>
                <th>{t('common.actions')}</th>
              </tr>
            </thead>
            <tbody>
              {orders.length === 0 ? (
                <tr>
                  <td colSpan={8}>
                    <div className="empty-table">{t('orders.empty')}</div>
                  </td>
                </tr>
              ) : (
                orders.map((order) => (
                  <tr key={order.id}>
                    <td>
                      <strong>{order.order_number}</strong>
                      <small>{t('common.id')} {order.id}</small>
                    </td>
                    <td>
                      <strong>{order.contact_name}</strong>
                      <small>{t('common.user')} {order.user_id}</small>
                    </td>
                    <td>
                      <span>{order.contact_phone}</span>
                      <small>{compactText(order.delivery_address, t('common.notProvided'))}</small>
                    </td>
                    <td>{formatMoney(order.total_amount, language)}</td>
                    <td>{order.promo_code_code ?? t('common.none')}</td>
                    <td>
                      <StatusBadge status={order.status} />
                    </td>
                    <td>{formatDate(order.created_at, language)}</td>
                    <td>
                      <div className="table-actions">
                        <button
                          className="text-button"
                          type="button"
                          onClick={() => selectOrderDetails(order)}
                        >
                          {t('common.details')}
                        </button>
                        <select
                          value={order.status}
                          onChange={(event) =>
                            updateOrderStatus(order, event.target.value as OrderStatus)
                          }
                        >
                          {orderStatuses.map((status) => (
                            <option key={status} value={status}>
                              {labelForEnum(status, t)}
                            </option>
                          ))}
                        </select>
                      </div>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>

        <aside className="detail-drawer">
          {selectedOrderLoading ? (
            <LoadingState title={t('orders.loadingDetails')} />
          ) : selectedOrder ? (
            <>
              <div className="section-heading">
                <div>
                  <h2>{selectedOrder.order_number}</h2>
                  <p>{t('orders.created', { date: formatDate(selectedOrder.created_at, language) })}</p>
                </div>
                <StatusBadge status={selectedOrder.status} />
              </div>
              <dl className="details-list">
                <div>
                  <dt>{t('orders.userId')}</dt>
                  <dd>
                    {selectedOrder.user_id}
                    <small className="muted-inline">{t('orders.userInfoFallback')}</small>
                  </dd>
                </div>
                <div>
                  <dt>{t('orders.customer')}</dt>
                  <dd>{selectedOrder.contact_name}</dd>
                </div>
                <div>
                  <dt>{t('orders.phone')}</dt>
                  <dd>{selectedOrder.contact_phone}</dd>
                </div>
                <div>
                  <dt>{t('orders.address')}</dt>
                  <dd>{selectedOrder.delivery_address}</dd>
                </div>
                <div>
                  <dt>{t('orders.comment')}</dt>
                  <dd>{compactText(selectedOrder.delivery_comment, t('common.notProvided'))}</dd>
                </div>
                <div>
                  <dt>{t('orders.promoCode')}</dt>
                  <dd>{selectedOrder.promo_code_code ?? t('common.none')}</dd>
                </div>
                <div>
                  <dt>{t('orders.subtotal')}</dt>
                  <dd>{formatMoney(selectedOrder.subtotal_amount, language)}</dd>
                </div>
                <div>
                  <dt>{t('orders.discount')}</dt>
                  <dd>{formatMoney(selectedOrder.discount_amount, language)}</dd>
                </div>
                <div>
                  <dt>{t('common.total')}</dt>
                  <dd>{formatMoney(selectedOrder.total_amount, language)}</dd>
                </div>
              </dl>
              <div className="section-heading order-detail-actions">
                <h3>{t('orders.items')}</h3>
                <select
                  value={selectedOrder.status}
                  onChange={(event) =>
                    updateOrderStatus(selectedOrder, event.target.value as OrderStatus)
                  }
                >
                  {orderStatuses.map((status) => (
                    <option key={status} value={status}>
                      {labelForEnum(status, t)}
                    </option>
                  ))}
                </select>
              </div>
              <div className="order-items-table">
                <table>
                  <thead>
                    <tr>
                      <th>{t('orders.item')}</th>
                      <th>{t('orders.variant')}</th>
                      <th>{t('orders.quantity')}</th>
                      <th>{t('orders.unitPrice')}</th>
                      <th>{t('orders.itemTotal')}</th>
                    </tr>
                  </thead>
                  <tbody>
                {selectedOrder.items.map((item) => (
                    <tr key={item.id}>
                      <td>
                        <div className="order-item-cell">
                          {item.product_thumbnail_url ? (
                            <img
                              className="order-item-thumb"
                              src={resolveMediaUrl(item.product_thumbnail_url)}
                              alt={item.product_title ?? item.product_name}
                            />
                          ) : (
                            <div className="order-item-thumb order-item-thumb-empty">
                              {t('orders.noThumbnail')}
                            </div>
                          )}
                          <div>
                            <strong>{item.product_title ?? item.product_name}</strong>
                            <small>
                              {t('common.id')} {item.product_id}
                            </small>
                            {!item.product_thumbnail_url ? (
                              <small>{t('orders.thumbnailGap')}</small>
                            ) : null}
                            <button
                              className="text-button"
                              type="button"
                              onClick={() => onNavigate(`/products/${item.product_id}/edit`)}
                            >
                              {t('orders.openProduct')}
                            </button>
                          </div>
                        </div>
                      </td>
                      <td>
                        <strong>{formatVariantSize(item.variant_size_grid, item.variant_size, t('productEditor.oneSize'))}</strong>
                        <small>{item.variant_color ?? t('common.notProvided')}</small>
                        <small>{item.variant_sku}</small>
                      </td>
                      <td>{item.quantity}</td>
                      <td>{formatMoney(item.unit_price, language)}</td>
                      <td>{formatMoney(item.item_total ?? item.subtotal, language)}</td>
                    </tr>
                ))}
                  </tbody>
                </table>
              </div>
            </>
          ) : (
            <div className="empty-drawer">{t('orders.selectDetails')}</div>
          )}
        </aside>
      </div>
    </div>
  );
}

function formatVariantSize(sizeGrid: ProductSizeGrid, size: string, oneSizeLabel: string): string {
  if (sizeGrid === 'shoes_ru') return `RU ${size}`;
  return size === 'ONE_SIZE' ? oneSizeLabel : size;
}
