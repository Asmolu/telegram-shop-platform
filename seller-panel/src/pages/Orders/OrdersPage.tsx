import { FormEvent, useEffect, useState } from 'react';
import { api } from '../../shared/api';
import type { Order, OrderStatus } from '../../shared/api';
import { ErrorState, LoadingState } from '../../shared/ui/DataState';
import { StatusBadge } from '../../shared/ui/StatusBadge';
import { compactText, formatDate, formatMoney } from '../../shared/utils/format';

interface PageProps {
  onAuthExpired: () => void;
}

interface OrderFilters {
  search: string;
  status: '' | OrderStatus;
}

const initialFilters: OrderFilters = { search: '', status: '' };
const orderStatuses: OrderStatus[] = ['NEW', 'PROCESSING', 'SHIPPED', 'DELIVERED', 'CANCELLED'];

export function OrdersPage({ onAuthExpired }: PageProps) {
  const [orders, setOrders] = useState<Order[]>([]);
  const [selectedOrder, setSelectedOrder] = useState<Order | null>(null);
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
    if (status === 'CANCELLED' && !window.confirm('Cancel this order?')) {
      return;
    }

    setNotice(null);
    try {
      const updated = await api.orders.updateStatus(order.id, status);
      setOrders((current) => current.map((item) => (item.id === updated.id ? updated : item)));
      setSelectedOrder((current) => (current?.id === updated.id ? updated : current));
      setNotice(`Order ${updated.order_number} updated.`);
    } catch (requestError) {
      setError(requestError);
    }
  }

  if (loading) return <LoadingState title="Loading orders" />;
  if (error) {
    return <ErrorState error={error} onRetry={loadOrders} onAuthExpired={onAuthExpired} />;
  }

  return (
    <div className="page-stack">
      <div className="page-toolbar">
        <form className="filters-row" onSubmit={applyFilters}>
          <label>
            <span>Search</span>
            <input
              value={draftFilters.search}
              onChange={(event) =>
                setDraftFilters((current) => ({ ...current, search: event.target.value }))
              }
              placeholder="Order number or customer"
            />
          </label>
          <label>
            <span>Status</span>
            <select
              value={draftFilters.status}
              onChange={(event) =>
                setDraftFilters((current) => ({
                  ...current,
                  status: event.target.value as OrderFilters['status'],
                }))
              }
            >
              <option value="">All statuses</option>
              {orderStatuses.map((status) => (
                <option key={status} value={status}>
                  {status.replace(/_/g, ' ')}
                </option>
              ))}
            </select>
          </label>
          <button className="button button-secondary" type="submit">
            Apply
          </button>
        </form>
      </div>

      {notice ? <div className="success-banner">{notice}</div> : null}

      <div className="split-view">
        <div className="table-panel">
          <table>
            <thead>
              <tr>
                <th>Order</th>
                <th>Customer</th>
                <th>Contact</th>
                <th>Total</th>
                <th>Promo</th>
                <th>Status</th>
                <th>Date</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {orders.length === 0 ? (
                <tr>
                  <td colSpan={8}>
                    <div className="empty-table">No orders match the current filters.</div>
                  </td>
                </tr>
              ) : (
                orders.map((order) => (
                  <tr key={order.id}>
                    <td>
                      <strong>{order.order_number}</strong>
                      <small>ID {order.id}</small>
                    </td>
                    <td>
                      <strong>{order.contact_name}</strong>
                      <small>User {order.user_id}</small>
                    </td>
                    <td>
                      <span>{order.contact_phone}</span>
                      <small>{compactText(order.delivery_address)}</small>
                    </td>
                    <td>{formatMoney(order.total_amount)}</td>
                    <td>{order.promo_code_code ?? 'None'}</td>
                    <td>
                      <StatusBadge status={order.status} />
                    </td>
                    <td>{formatDate(order.created_at)}</td>
                    <td>
                      <div className="table-actions">
                        <button
                          className="text-button"
                          type="button"
                          onClick={() => setSelectedOrder(order)}
                        >
                          Details
                        </button>
                        <select
                          value={order.status}
                          onChange={(event) =>
                            updateOrderStatus(order, event.target.value as OrderStatus)
                          }
                        >
                          {orderStatuses.map((status) => (
                            <option key={status} value={status}>
                              {status.replace(/_/g, ' ')}
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
          {selectedOrder ? (
            <>
              <div className="section-heading">
                <div>
                  <h2>{selectedOrder.order_number}</h2>
                  <p>Created {formatDate(selectedOrder.created_at)}</p>
                </div>
                <StatusBadge status={selectedOrder.status} />
              </div>
              <dl className="details-list">
                <div>
                  <dt>Customer</dt>
                  <dd>{selectedOrder.contact_name}</dd>
                </div>
                <div>
                  <dt>Phone</dt>
                  <dd>{selectedOrder.contact_phone}</dd>
                </div>
                <div>
                  <dt>Address</dt>
                  <dd>{selectedOrder.delivery_address}</dd>
                </div>
                <div>
                  <dt>Comment</dt>
                  <dd>{compactText(selectedOrder.delivery_comment)}</dd>
                </div>
                <div>
                  <dt>Promo code</dt>
                  <dd>{selectedOrder.promo_code_code ?? 'None'}</dd>
                </div>
                <div>
                  <dt>Subtotal</dt>
                  <dd>{formatMoney(selectedOrder.subtotal_amount)}</dd>
                </div>
                <div>
                  <dt>Discount</dt>
                  <dd>{formatMoney(selectedOrder.discount_amount)}</dd>
                </div>
                <div>
                  <dt>Total</dt>
                  <dd>{formatMoney(selectedOrder.total_amount)}</dd>
                </div>
              </dl>
              <h3>Items</h3>
              <div className="drawer-list">
                {selectedOrder.items.map((item) => (
                  <div key={item.id}>
                    <strong>{item.product_name}</strong>
                    <span>
                      {item.variant_size} / {item.variant_sku} / qty {item.quantity}
                    </span>
                    <small>{formatMoney(item.subtotal)}</small>
                  </div>
                ))}
              </div>
            </>
          ) : (
            <div className="empty-drawer">Select an order to see details.</div>
          )}
        </aside>
      </div>
    </div>
  );
}
