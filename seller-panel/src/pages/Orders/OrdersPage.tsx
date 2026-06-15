import { FormEvent, useEffect, useState } from 'react';
import { ApiError, api, resolveMediaUrl } from '../../shared/api';
import type {
  ManualPayment,
  ManualPaymentStatus,
  Order,
  OrderStatus,
  ProductSizeGrid,
} from '../../shared/api';
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
const paymentStatuses: ManualPaymentStatus[] = [
  'PENDING',
  'SUBMITTED',
  'APPROVED',
  'REJECTED',
  'EXPIRED',
  'CANCELLED',
];

export function OrdersPage({ onNavigate, onAuthExpired }: PageProps) {
  const { language, t } = useI18n();
  const [orders, setOrders] = useState<Order[]>([]);
  const [payments, setPayments] = useState<ManualPayment[]>([]);
  const [paymentFilter, setPaymentFilter] = useState<'' | ManualPaymentStatus>('SUBMITTED');
  const [selectedPayment, setSelectedPayment] = useState<ManualPayment | null>(null);
  const [paymentBusy, setPaymentBusy] = useState(false);
  const [rejectReason, setRejectReason] = useState('Деньги не поступили');
  const [selectedOrder, setSelectedOrder] = useState<Order | null>(null);
  const [selectedOrderLoading, setSelectedOrderLoading] = useState(false);
  const [messageOrder, setMessageOrder] = useState<Order | null>(null);
  const [messageText, setMessageText] = useState('');
  const [messagePhoto, setMessagePhoto] = useState<File | null>(null);
  const [messageBusy, setMessageBusy] = useState(false);
  const [messageError, setMessageError] = useState<string | null>(null);
  const [messageSuccess, setMessageSuccess] = useState<string | null>(null);
  const [messageFileKey, setMessageFileKey] = useState(0);
  const [filters, setFilters] = useState<OrderFilters>(initialFilters);
  const [draftFilters, setDraftFilters] = useState<OrderFilters>(initialFilters);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<unknown>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  async function loadOrders(showLoader = true) {
    if (showLoader) setLoading(true);
    setError(null);

    try {
      const [orderList, paymentList] = await Promise.all([
        api.orders.listAdmin({
          limit: 100,
          offset: 0,
          search: filters.search,
          status: filters.status,
        }),
        api.manualPayments.list(paymentFilter || undefined),
      ]);
      setOrders(orderList.items);
      setPayments(paymentList.items);
      const requestedPaymentId = Number(new URLSearchParams(window.location.search).get('payment'));
      if (Number.isFinite(requestedPaymentId) && requestedPaymentId > 0) {
        void selectPaymentDetails(requestedPaymentId);
      }
    } catch (requestError) {
      setError(requestError);
    } finally {
      if (showLoader) setLoading(false);
    }
  }

  useEffect(() => {
    void loadOrders();
  }, [filters, paymentFilter]);

  function applyFilters(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setFilters(draftFilters);
  }

  async function updateOrderStatus(order: Order, status: OrderStatus) {
    if (status === 'CANCELLED' && !window.confirm(t('orders.cancelConfirm'))) {
      return;
    }

    setNotice(null);
    setActionError(null);
    try {
      const updated = await api.orders.updateStatus(order.id, status);
      setOrders((current) => current.map((item) => (item.id === updated.id ? updated : item)));
      setSelectedOrder((current) => (current?.id === updated.id ? updated : current));
      setNotice(t('orders.updated', { orderNumber: updated.order_number }));
    } catch (requestError) {
      setActionError(formatRequestError(requestError));
      await refreshOrder(order.id);
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

  async function selectPaymentDetails(paymentId: number) {
    setPaymentBusy(true);
    setError(null);
    setActionError(null);
    try {
      const payment = await api.manualPayments.get(paymentId);
      setSelectedPayment(payment);
      setRejectReason(payment.reject_reason || 'Деньги не поступили');
    } catch (requestError) {
      setError(requestError);
    } finally {
      setPaymentBusy(false);
    }
  }

  async function approvePayment(payment: ManualPayment) {
    if (!window.confirm(`Подтвердить оплату заказа ${payment.order_number}?`)) return;
    setPaymentBusy(true);
    setActionError(null);
    setNotice(null);
    try {
      const updated = await api.manualPayments.approve(payment.id);
      updatePaymentState(updated);
      setNotice(`Оплата заказа ${updated.order_number} подтверждена.`);
    } catch (requestError) {
      await recoverPaymentMutation(payment, 'APPROVED', requestError);
    } finally {
      setPaymentBusy(false);
    }
  }

  async function rejectPayment(payment: ManualPayment) {
    if (!window.confirm(`Отклонить оплату заказа ${payment.order_number}?`)) return;
    setPaymentBusy(true);
    setActionError(null);
    setNotice(null);
    try {
      const updated = await api.manualPayments.reject(payment.id, rejectReason);
      updatePaymentState(updated);
      setNotice(`Оплата заказа ${updated.order_number} отклонена, резерв снят.`);
    } catch (requestError) {
      await recoverPaymentMutation(payment, 'REJECTED', requestError);
    } finally {
      setPaymentBusy(false);
    }
  }

  function updatePaymentState(updated: ManualPayment) {
    setPayments((current) => {
      if (paymentFilter && updated.status !== paymentFilter) {
        return current.filter((item) => item.id !== updated.id);
      }
      return current.map((item) => (item.id === updated.id ? updated : item));
    });
    setSelectedPayment(updated);
    setOrders((current) => current.map((order) => updateOrderFromPayment(order, updated)));
    setSelectedOrder((current) => (
      current ? updateOrderFromPayment(current, updated) : current
    ));
  }

  async function refreshOrder(orderId: number) {
    try {
      const refreshed = await api.orders.getAdmin(orderId);
      setOrders((current) => current.map((order) => (
        order.id === refreshed.id ? refreshed : order
      )));
      setSelectedOrder((current) => (
        current?.id === refreshed.id ? refreshed : current
      ));
      return refreshed;
    } catch {
      return null;
    }
  }

  async function recoverPaymentMutation(
    payment: ManualPayment,
    expectedStatus: ManualPaymentStatus,
    requestError: unknown,
  ) {
    const [paymentResult, orderResult] = await Promise.allSettled([
      api.manualPayments.get(payment.id),
      refreshOrder(payment.order_id),
    ]);
    if (paymentResult.status === 'fulfilled') {
      updatePaymentState(paymentResult.value);
      if (paymentResult.value.status === expectedStatus) {
        setActionError(null);
        setNotice(
          expectedStatus === 'APPROVED'
            ? `Оплата заказа ${paymentResult.value.order_number} подтверждена.`
            : `Оплата заказа ${paymentResult.value.order_number} отклонена, резерв снят.`,
        );
        return;
      }
    }
    const recoveryMessage = paymentResult.status === 'fulfilled'
      || (orderResult.status === 'fulfilled' && orderResult.value !== null)
      ? 'Состояние оплаты и заказа обновлено повторным запросом.'
      : 'Не удалось повторно загрузить состояние оплаты и заказа.';
    setActionError(
      `${formatRequestError(requestError)} ${recoveryMessage}`,
    );
  }

  function openCustomerMessage(order: Order) {
    setMessageOrder(order);
    setMessageText('');
    setMessagePhoto(null);
    setMessageError(null);
    setMessageSuccess(null);
    setMessageFileKey((current) => current + 1);
  }

  function closeCustomerMessage() {
    if (messageBusy) return;
    setMessageOrder(null);
  }

  async function sendCustomerMessage(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!messageOrder) return;
    if (!messageText.trim() && !messagePhoto) {
      setMessageError('Введите текст или выберите фотографию.');
      return;
    }
    if (messagePhoto && messagePhoto.size > 5 * 1024 * 1024) {
      setMessageError('Фотография не должна превышать 5 МБ.');
      return;
    }

    setMessageBusy(true);
    setMessageError(null);
    setMessageSuccess(null);
    try {
      await api.orders.sendCustomerMessage(messageOrder.id, messageText, messagePhoto);
      setMessageSuccess('Сообщение отправлено покупателю через Bot 1.');
      setMessageText('');
      setMessagePhoto(null);
      setMessageFileKey((current) => current + 1);
    } catch (requestError) {
      setMessageError(formatRequestError(requestError));
    } finally {
      setMessageBusy(false);
    }
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
      {actionError ? <div className="error-banner">{actionError}</div> : null}

      <section className="panel payment-review-panel">
        <div className="section-heading">
          <div>
            <h2>Проверка ручных оплат</h2>
            <p>Подтвердите поступление полной суммы или отклоните оплату и снимите резерв.</p>
          </div>
          <label className="payment-filter-field">
            <span>Статус оплаты</span>
            <select
              value={paymentFilter}
              onChange={(event) =>
                setPaymentFilter(event.target.value as '' | ManualPaymentStatus)
              }
            >
              <option value="">Все статусы</option>
              {paymentStatuses.map((status) => (
                <option key={status} value={status}>{paymentStatusLabel(status)}</option>
              ))}
            </select>
          </label>
        </div>

        <div className="payment-review-layout">
          <div className="payment-review-list">
            {payments.length === 0 ? (
              <div className="empty-table">Нет оплат с выбранным статусом.</div>
            ) : payments.map((payment) => (
              <button
                className={`payment-review-row ${payment.status === 'SUBMITTED' ? 'is-submitted' : ''}`}
                key={payment.id}
                type="button"
                onClick={() => void selectPaymentDetails(payment.id)}
              >
                <span>
                  <strong>{payment.order_number}</strong>
                  <small>{payment.customer_name} · {payment.customer_phone}</small>
                </span>
                <span>
                  <strong>{formatMoney(payment.amount, language)}</strong>
                  <small>{paymentStatusLabel(payment.status)}</small>
                </span>
              </button>
            ))}
          </div>

          <aside className="payment-review-detail">
            {paymentBusy && !selectedPayment ? (
              <LoadingState title="Загружаем оплату" />
            ) : selectedPayment ? (
              <>
                <div className="section-heading">
                  <div>
                    <h3>{selectedPayment.order_number}</h3>
                    <p>{paymentStatusLabel(selectedPayment.status)}</p>
                  </div>
                  <StatusBadge
                    status={selectedPayment.status}
                    label={paymentStatusLabel(selectedPayment.status)}
                  />
                </div>
                <dl className="details-list payment-details-list">
                  <div>
                    <dt>Статус оплаты</dt>
                    <dd><StatusBadge status={selectedPayment.status} label={paymentStatusLabel(selectedPayment.status)} /></dd>
                  </div>
                  <div>
                    <dt>Статус заказа</dt>
                    <dd><StatusBadge status={selectedPayment.order_status} /></dd>
                  </div>
                  <div><dt>Клиент</dt><dd>{selectedPayment.customer_name}</dd></div>
                  <div><dt>Телефон клиента</dt><dd>{selectedPayment.customer_phone}</dd></div>
                  <div><dt>{t('orders.deliveryMethod')}</dt><dd>{labelForEnum(selectedPayment.delivery_method, t)}</dd></div>
                  <div><dt>Сумма</dt><dd>{formatMoney(selectedPayment.amount, language)}</dd></div>
                  <div><dt>Телефон СБП</dt><dd>{selectedPayment.seller_phone_display}</dd></div>
                  <div><dt>Комментарий</dt><dd>{selectedPayment.payment_comment}</dd></div>
                  <div><dt>Отправлено</dt><dd>{selectedPayment.submitted_at ? formatDate(selectedPayment.submitted_at, language) : 'Не отправлено'}</dd></div>
                  <div><dt>Резерв до</dt><dd>{formatDate(selectedPayment.expires_at, language)}</dd></div>
                </dl>

                {selectedPayment.receipt_image_url ? (
                  <a
                    className="payment-receipt-preview"
                    href={resolveMediaUrl(selectedPayment.receipt_image_url)}
                    rel="noreferrer"
                    target="_blank"
                  >
                    <img
                      src={resolveMediaUrl(selectedPayment.receipt_image_url)}
                      alt="Скриншот оплаты"
                    />
                    <span>Открыть скриншот</span>
                  </a>
                ) : <div className="empty-table">Скриншот не загружен.</div>}

                {['PENDING', 'SUBMITTED'].includes(selectedPayment.status) ? (
                  <div className="payment-decision-box">
                      <label>
                        <span>Причина отклонения</span>
                        <input
                          list="payment-reject-reasons"
                          maxLength={500}
                          value={rejectReason}
                          onChange={(event) => setRejectReason(event.target.value)}
                        />
                        <datalist id="payment-reject-reasons">
                          <option value="Деньги не поступили" />
                          <option value="Неверная сумма" />
                          <option value="Неверный комментарий" />
                        </datalist>
                      </label>
                    <div className="payment-decision-actions">
                      <button
                        className="button button-primary"
                        disabled={paymentBusy}
                        type="button"
                        onClick={() => void approvePayment(selectedPayment)}
                      >
                        Подтвердить оплату
                      </button>
                      <button
                        className="button button-danger"
                        disabled={paymentBusy}
                        type="button"
                        onClick={() => void rejectPayment(selectedPayment)}
                      >
                        Отклонить оплату
                      </button>
                    </div>
                  </div>
                ) : null}
              </>
            ) : <div className="empty-drawer">Выберите оплату для проверки.</div>}
          </aside>
        </div>
      </section>

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
                <th>Статус оплаты</th>
                <th>Статус заказа</th>
                <th>{t('common.date')}</th>
                <th>{t('common.actions')}</th>
              </tr>
            </thead>
            <tbody>
              {orders.length === 0 ? (
                <tr>
                  <td colSpan={9}>
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
                      <small>{labelForEnum(order.delivery_method, t)}</small>
                    </td>
                    <td>{formatMoney(order.total_amount, language)}</td>
                    <td>{order.promo_code_code ?? t('common.none')}</td>
                    <td>
                      {order.manual_payment ? (
                        <StatusBadge
                          status={order.manual_payment.status}
                          label={paymentStatusLabel(order.manual_payment.status)}
                        />
                      ) : <span className="muted-inline">—</span>}
                    </td>
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
                          disabled={Boolean(order.manual_payment && ['PENDING', 'SUBMITTED'].includes(order.manual_payment.status))}
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
                <button
                  className="button button-secondary button-compact"
                  type="button"
                  onClick={() => openCustomerMessage(selectedOrder)}
                >
                  Отправить сообщение
                </button>
              </div>
              <div className="order-status-summary">
                <div>
                  <span>Статус оплаты</span>
                  {selectedOrder.manual_payment ? (
                    <StatusBadge
                      status={selectedOrder.manual_payment.status}
                      label={paymentStatusLabel(selectedOrder.manual_payment.status)}
                    />
                  ) : <span className="muted-inline">—</span>}
                </div>
                <div>
                  <span>Статус заказа</span>
                  <StatusBadge status={selectedOrder.status} />
                </div>
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
                  <dt>{t('orders.deliveryMethod')}</dt>
                  <dd>{labelForEnum(selectedOrder.delivery_method, t)}</dd>
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
                  disabled={Boolean(selectedOrder.manual_payment && ['PENDING', 'SUBMITTED'].includes(selectedOrder.manual_payment.status))}
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
      {messageOrder ? (
        <div
          className="customer-message-modal"
          role="presentation"
          onMouseDown={(event) => {
            if (event.target === event.currentTarget) closeCustomerMessage();
          }}
        >
          <form
            aria-labelledby="customer-message-title"
            className="customer-message-modal__surface"
            role="dialog"
            onSubmit={sendCustomerMessage}
          >
            <div className="section-heading">
              <div>
                <h2 id="customer-message-title">Сообщение покупателю</h2>
                <p>{messageOrder.order_number} · Bot 1</p>
              </div>
              <button
                aria-label="Закрыть"
                className="customer-message-modal__close"
                disabled={messageBusy}
                type="button"
                onClick={closeCustomerMessage}
              >
                ×
              </button>
            </div>

            <label>
              <span>Текст</span>
              <textarea
                maxLength={messagePhoto ? 1024 : 4096}
                rows={6}
                value={messageText}
                onChange={(event) => setMessageText(event.target.value)}
              />
            </label>

            <label>
              <span>Фотография</span>
              <input
                accept="image/jpeg,image/png,image/webp"
                key={messageFileKey}
                type="file"
                onChange={(event) => setMessagePhoto(event.target.files?.[0] ?? null)}
              />
              {messagePhoto ? <small>{messagePhoto.name}</small> : null}
            </label>

            {messageSuccess ? <div className="success-banner">{messageSuccess}</div> : null}
            {messageError ? <div className="error-banner">{messageError}</div> : null}

            <div className="form-actions">
              <button
                className="button button-secondary"
                disabled={messageBusy}
                type="button"
                onClick={closeCustomerMessage}
              >
                Закрыть
              </button>
              <button
                className="button button-primary"
                disabled={messageBusy || (!messageText.trim() && !messagePhoto)}
                type="submit"
              >
                {messageBusy ? 'Отправляем...' : 'Отправить'}
              </button>
            </div>
          </form>
        </div>
      ) : null}
    </div>
  );
}

function formatVariantSize(sizeGrid: ProductSizeGrid, size: string, oneSizeLabel: string): string {
  if (sizeGrid === 'shoes_ru') return `RU ${size}`;
  return size === 'ONE_SIZE' ? oneSizeLabel : size;
}

function paymentStatusLabel(status: ManualPaymentStatus): string {
  return {
    PENDING: 'Ожидает оплату',
    SUBMITTED: 'Оплата на проверке',
    APPROVED: 'Оплачено',
    REJECTED: 'Отклонено',
    EXPIRED: 'Истекло время оплаты',
    CANCELLED: 'Отменено',
  }[status];
}

function updateOrderFromPayment(order: Order, payment: ManualPayment): Order {
  if (order.id !== payment.order_id) return order;
  return {
    ...order,
    status: payment.order_status,
    manual_payment: {
      id: payment.id,
      status: payment.status,
      expires_at: payment.expires_at,
      submitted_at: payment.submitted_at,
      receipt_image_path: payment.receipt_image_path,
    },
  };
}

function formatRequestError(error: unknown): string {
  if (error instanceof ApiError || error instanceof Error) {
    return error.message;
  }
  return 'Запрос не выполнен. Повторите попытку.';
}
