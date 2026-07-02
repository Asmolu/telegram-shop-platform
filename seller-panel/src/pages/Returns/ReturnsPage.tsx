import { type FormEvent, useEffect, useMemo, useState } from 'react';
import { ApiError, api, resolveMediaUrl } from '../../shared/api';
import type {
  ReturnProcessPayload,
  ReturnRequest,
  ReturnRequestItem,
  ReturnRequestStatus,
} from '../../shared/api';
import { useI18n } from '../../shared/i18n';
import { ErrorState, LoadingState } from '../../shared/ui/DataState';
import { StatusBadge } from '../../shared/ui/StatusBadge';
import { compactText, formatDate, formatMoney } from '../../shared/utils/format';

interface PageProps {
  initialReturnRequestId?: number;
  onNavigate: (path: string) => void;
  onAuthExpired: () => void;
}

const returnStatuses: ReturnRequestStatus[] = [
  'PENDING',
  'APPROVED',
  'REJECTED',
  'COMPLETED',
  'CANCELLED',
];

const returnStatusLabels: Record<'ru' | 'en', Record<ReturnRequestStatus, string>> = {
  ru: {
    PENDING: 'Ожидает',
    APPROVED: 'Одобрено',
    REJECTED: 'Отклонено',
    COMPLETED: 'Завершено',
    CANCELLED: 'Отменено',
  },
  en: {
    PENDING: 'Pending',
    APPROVED: 'Approved',
    REJECTED: 'Rejected',
    COMPLETED: 'Completed',
    CANCELLED: 'Cancelled',
  },
};

export function ReturnsPage({
  initialReturnRequestId,
  onAuthExpired,
  onNavigate,
}: PageProps) {
  const { language, t } = useI18n();
  const [statusFilter, setStatusFilter] = useState<'' | ReturnRequestStatus>('');
  const [search, setSearch] = useState('');
  const [returnRequests, setReturnRequests] = useState<ReturnRequest[]>([]);
  const [selectedReturn, setSelectedReturn] = useState<ReturnRequest | null>(null);
  const [loading, setLoading] = useState(true);
  const [detailLoading, setDetailLoading] = useState(false);
  const [actionBusy, setActionBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  useEffect(() => {
    void loadReturns();
  }, [statusFilter, initialReturnRequestId]);

  const filteredRequests = useMemo(() => {
    const needle = search.trim().toLowerCase();
    if (!needle) {
      return returnRequests;
    }
    return returnRequests.filter((request) => (
      request.return_number.toLowerCase().includes(needle)
      || String(request.id).includes(needle)
      || String(request.order_id).includes(needle)
      || (request.order_number ?? '').toLowerCase().includes(needle)
      || (request.customer_name ?? '').toLowerCase().includes(needle)
      || (request.customer_phone ?? '').toLowerCase().includes(needle)
    ));
  }, [returnRequests, search]);

  async function loadReturns(showLoader = true) {
    if (showLoader) setLoading(true);
    setError(null);
    try {
      const result = await api.returns.list({
        limit: 100,
        offset: 0,
        status: statusFilter,
      });
      setReturnRequests(result.items);
      const targetId = initialReturnRequestId ?? selectedReturn?.id ?? result.items[0]?.id;
      if (targetId) {
        await selectReturnDetails(targetId, false);
      } else {
        setSelectedReturn(null);
      }
    } catch (requestError) {
      setError(requestError);
    } finally {
      if (showLoader) setLoading(false);
    }
  }

  async function selectReturnDetails(returnRequestId: number, updateRoute = true) {
    if (updateRoute) {
      onNavigate(`/returns/${returnRequestId}`);
      return;
    }
    setDetailLoading(true);
    setActionError(null);
    try {
      const detail = await api.returns.get(returnRequestId);
      setSelectedReturn(detail);
    } catch (requestError) {
      setError(requestError);
    } finally {
      setDetailLoading(false);
    }
  }

  function applyReturnUpdate(updated: ReturnRequest) {
    setSelectedReturn(updated);
    setReturnRequests((current) => (
      current.map((request) => (request.id === updated.id ? updated : request))
    ));
    setNotice(t('returns.decisionSaved', {
      number: updated.return_number,
      status: returnStatusLabel(updated.status, language).toLowerCase(),
    }));
  }

  async function decideReturn(nextStatus: 'APPROVED' | 'REJECTED') {
    if (!selectedReturn || selectedReturn.status !== 'PENDING') {
      return;
    }
    const decisionComment = window.prompt(t('returns.decisionPrompt'), '') ?? null;
    if (decisionComment === null) {
      return;
    }

    setActionBusy(true);
    setActionError(null);
    setNotice(null);
    try {
      const updated = nextStatus === 'APPROVED'
        ? await api.returns.approve(selectedReturn.id, { decision_comment: decisionComment })
        : await api.returns.reject(selectedReturn.id, { decision_comment: decisionComment });
      applyReturnUpdate(updated);
    } catch (requestError) {
      setActionError(formatRequestError(requestError));
    } finally {
      setActionBusy(false);
    }
  }

  async function completeReturn() {
    if (!selectedReturn || selectedReturn.status !== 'APPROVED') {
      return;
    }
    const comment = window.prompt(t('returns.completePrompt'), '') ?? null;
    if (comment === null) {
      return;
    }

    setActionBusy(true);
    setActionError(null);
    setNotice(null);
    try {
      const updated = await api.returns.complete(selectedReturn.id, { comment });
      applyReturnUpdate(updated);
    } catch (requestError) {
      setActionError(formatRequestError(requestError));
    } finally {
      setActionBusy(false);
    }
  }

  async function processReturn(payload: ReturnProcessPayload) {
    if (!selectedReturn || selectedReturn.status !== 'APPROVED') {
      return;
    }

    setActionBusy(true);
    setActionError(null);
    setNotice(null);
    try {
      const updated = await api.returns.process(selectedReturn.id, payload);
      applyReturnUpdate(updated);
    } catch (requestError) {
      setActionError(formatRequestError(requestError));
    } finally {
      setActionBusy(false);
    }
  }

  async function cancelReturn() {
    if (!selectedReturn || !['PENDING', 'APPROVED'].includes(selectedReturn.status)) {
      return;
    }
    const comment = window.prompt(t('returns.cancelPrompt'), '') ?? null;
    if (comment === null) {
      return;
    }

    setActionBusy(true);
    setActionError(null);
    setNotice(null);
    try {
      const updated = await api.returns.cancel(selectedReturn.id, { comment });
      applyReturnUpdate(updated);
    } catch (requestError) {
      setActionError(formatRequestError(requestError));
    } finally {
      setActionBusy(false);
    }
  }

  return (
    <div className="page-stack returns-page">
      <div className="filters-row">
        <label>
          <span>{t('common.status')}</span>
          <select
            value={statusFilter}
            onChange={(event) => setStatusFilter(event.target.value as '' | ReturnRequestStatus)}
          >
            <option value="">{t('common.all')}</option>
            {returnStatuses.map((status) => (
              <option value={status} key={status}>
                {returnStatusLabel(status, language)}
              </option>
            ))}
          </select>
        </label>
        <label>
          <span>{t('common.search')}</span>
          <input
            value={search}
            placeholder={t('returns.searchPlaceholder')}
            onChange={(event) => setSearch(event.target.value)}
          />
        </label>
      </div>

      {notice ? <div className="success-banner">{notice}</div> : null}
      {loading ? <LoadingState title={t('returns.loading')} /> : null}
      {error ? <ErrorState error={error} onRetry={() => void loadReturns()} onAuthExpired={onAuthExpired} /> : null}

      {!loading && !error ? (
        <div className="returns-layout">
          <div className="table-panel returns-table-panel">
            <table>
              <thead>
                <tr>
                  <th>{t('returns.request')}</th>
                  <th>{t('orders.order')}</th>
                  <th>{t('returns.customer')}</th>
                  <th>{t('common.status')}</th>
                  <th>{t('common.created')}</th>
                  <th>{t('returns.items')}</th>
                  <th>{t('returns.reason')}</th>
                </tr>
              </thead>
              <tbody>
                {filteredRequests.length === 0 ? (
                  <tr>
                    <td colSpan={7}>
                      <div className="empty-table">{t('returns.empty')}</div>
                    </td>
                  </tr>
                ) : (
                  filteredRequests.map((returnRequest) => (
                    <tr
                      className={selectedReturn?.id === returnRequest.id ? 'selected-row' : ''}
                      key={returnRequest.id}
                      onClick={() => void selectReturnDetails(returnRequest.id)}
                    >
                      <td>
                        <strong>{returnRequest.return_number}</strong>
                        <small>ID {returnRequest.id}</small>
                      </td>
                      <td>
                        <strong>{returnRequest.order_number ?? `#${returnRequest.order_id}`}</strong>
                        <small>ID {returnRequest.order_id}</small>
                      </td>
                      <td>
                        <strong>{compactText(returnRequest.customer_name, t('common.notProvided'))}</strong>
                        <small>{compactText(returnRequest.customer_phone, t('common.notProvided'))}</small>
                      </td>
                      <td>
                        <StatusBadge
                          status={returnRequest.status}
                          label={returnStatusLabel(returnRequest.status, language)}
                        />
                      </td>
                      <td>{formatDate(returnRequest.created_at, language)}</td>
                      <td>{returnRequest.items.length}</td>
                      <td className="returns-reason-preview">{returnRequest.reason}</td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>

          <ReturnDetail
            actionBusy={actionBusy}
            actionError={actionError}
            detailLoading={detailLoading}
            onApprove={() => void decideReturn('APPROVED')}
            onCancel={() => void cancelReturn()}
            onComplete={() => void completeReturn()}
            onProcess={(payload) => processReturn(payload)}
            onReject={() => void decideReturn('REJECTED')}
            onOpenOrder={() => onNavigate('/orders')}
            returnRequest={selectedReturn}
          />
        </div>
      ) : null}
    </div>
  );
}

function ReturnDetail({
  actionBusy,
  actionError,
  detailLoading,
  onApprove,
  onCancel,
  onComplete,
  onReject,
  onProcess,
  onOpenOrder,
  returnRequest,
}: {
  actionBusy: boolean;
  actionError: string | null;
  detailLoading: boolean;
  onApprove: () => void;
  onCancel: () => void;
  onComplete: () => void;
  onReject: () => void;
  onProcess: (payload: ReturnProcessPayload) => Promise<void>;
  onOpenOrder: () => void;
  returnRequest: ReturnRequest | null;
}) {
  const { language, t } = useI18n();
  const [refundAmount, setRefundAmount] = useState('0.00');
  const [refundMethod, setRefundMethod] = useState('manual_cash');
  const [refundComment, setRefundComment] = useState('');
  const [restockQuantities, setRestockQuantities] = useState<Record<number, number>>({});
  const [completeAfterProcessing, setCompleteAfterProcessing] = useState(true);
  const [processingComment, setProcessingComment] = useState('');
  const [processingValidationError, setProcessingValidationError] = useState<string | null>(null);

  useEffect(() => {
    if (!returnRequest) {
      return;
    }

    setRefundAmount(
      toMoneyInputValue(
        returnRequest.refund?.amount
          ?? returnRequest.total_return_amount
          ?? calculateReturnTotal(returnRequest),
      ),
    );
    setRefundMethod(returnRequest.refund?.method ?? 'manual_cash');
    setRefundComment(returnRequest.refund?.comment ?? '');
    setRestockQuantities(
      Object.fromEntries(returnRequest.items.map((item) => [item.id, 0])),
    );
    setCompleteAfterProcessing(true);
    setProcessingComment('');
    setProcessingValidationError(null);
  }, [returnRequest?.id, returnRequest?.status, returnRequest?.updated_at]);

  if (detailLoading) {
    return <div className="detail-drawer"><LoadingState title={t('returns.detailLoading')} /></div>;
  }
  if (!returnRequest) {
    return <div className="detail-drawer empty-drawer">{t('returns.selectRequest')}</div>;
  }

  const canProcess = returnRequest.status === 'APPROVED' && (returnRequest.can_process ?? true);
  const hasRestockAudit = returnRequest.items.some((item) => itemRestockedQuantity(item) > 0);

  async function submitProcessing(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const detail = returnRequest;
    if (!detail) {
      return;
    }
    const amount = parseMoneyInput(refundAmount);
    const total = Number(detail.total_return_amount ?? calculateReturnTotal(detail));
    if (amount === null) {
      setProcessingValidationError(t('returns.refundAmountInvalid'));
      return;
    }
    if (amount < 0) {
      setProcessingValidationError(t('returns.refundAmountNegative'));
      return;
    }
    if (amount > total) {
      setProcessingValidationError(t('returns.refundAmountTooHigh'));
      return;
    }

    const restockItems: ReturnProcessPayload['restock_items'] = [];
    for (const item of detail.items) {
      const additionalQuantity = Number(restockQuantities[item.id] ?? 0);
      const remainingQuantity = itemRemainingRestockableQuantity(item);
      if (additionalQuantity < 0) {
        setProcessingValidationError(t('returns.restockQuantityNegative'));
        return;
      }
      if (additionalQuantity > remainingQuantity) {
        setProcessingValidationError(t('returns.restockQuantityTooHigh'));
        return;
      }
      if (additionalQuantity > 0 && !item.product_variant_id) {
        setProcessingValidationError(t('returns.restockNoVariant'));
        return;
      }
      if (additionalQuantity > 0) {
        restockItems.push({
          return_request_item_id: item.id,
          quantity: itemRestockedQuantity(item) + additionalQuantity,
        });
      }
    }

    setProcessingValidationError(null);
    await onProcess({
      refund: {
        amount: amount.toFixed(2),
        currency: 'RUB',
        method: refundMethod,
        comment: refundComment.trim() || null,
      },
      restock_items: restockItems,
      complete: completeAfterProcessing,
      comment: processingComment.trim() || null,
    });
  }

  function setItemRestockChecked(item: ReturnRequestItem, checked: boolean) {
    setRestockQuantities((current) => ({
      ...current,
      [item.id]: checked ? Math.min(itemRemainingRestockableQuantity(item), 1) : 0,
    }));
    setProcessingValidationError(null);
  }

  function setItemRestockQuantity(item: ReturnRequestItem, quantity: number) {
    setRestockQuantities((current) => ({
      ...current,
      [item.id]: Number.isFinite(quantity) ? quantity : 0,
    }));
    setProcessingValidationError(null);
  }

  return (
    <aside className="detail-drawer returns-detail">
      <div className="returns-detail__header">
        <div>
          <h2>{returnRequest.return_number}</h2>
          <p>{t('orders.order')} {returnRequest.order_number ?? `#${returnRequest.order_id}`}</p>
        </div>
        <StatusBadge
          status={returnRequest.status}
          label={returnStatusLabel(returnRequest.status, language)}
        />
      </div>

      <dl className="details-list">
        <div><dt>{t('returns.customer')}</dt><dd>{compactText(returnRequest.customer_name, t('common.notProvided'))}</dd></div>
        <div><dt>{t('returns.contact')}</dt><dd>{compactText(returnRequest.customer_phone, t('common.notProvided'))}</dd></div>
        <div><dt>{t('common.created')}</dt><dd>{formatDate(returnRequest.created_at, language)}</dd></div>
        <div><dt>{t('returns.reason')}</dt><dd>{returnRequest.reason}</dd></div>
        <div><dt>{t('returns.comment')}</dt><dd>{compactText(returnRequest.comment, t('common.notProvided'))}</dd></div>
      </dl>

      <button
        className="text-button"
        type="button"
        onClick={onOpenOrder}
      >
        {t('returns.openOrder')}
      </button>

      <h3>{t('returns.items')}</h3>
      <div className="returns-item-list">
        {returnRequest.items.map((item) => (
          <article className="returns-item" key={item.id}>
            <strong>{item.product_name}</strong>
            <small>{[item.product_brand, item.sku, item.color, item.size].filter(Boolean).join(' · ')}</small>
            <span>{item.quantity} × {formatMoney(item.unit_price, language)}</span>
          </article>
        ))}
      </div>

      <h3>{t('returns.attachments')}</h3>
      {returnRequest.attachments.length > 0 ? (
        <div className="returns-attachments">
          {returnRequest.attachments.map((attachment) => {
            const mediaUrl = resolveMediaUrl(attachment.url || attachment.file_path);
            return (
              <a
                className="returns-attachment"
                href={mediaUrl}
                key={attachment.id}
                rel="noreferrer"
                target="_blank"
              >
                {attachment.media_type === 'image' ? (
                  <img src={mediaUrl} alt="" loading="lazy" />
                ) : (
                  <span>{t('returns.video')}</span>
                )}
                <small>{attachment.original_filename}</small>
              </a>
            );
          })}
        </div>
      ) : (
        <p className="muted-text">{t('returns.noAttachments')}</p>
      )}

      {canProcess ? (
        <form className="returns-processing" onSubmit={submitProcessing}>
          <h3>{t('returns.processing')}</h3>
          <div className="returns-processing__grid">
            <label>
              <span>{t('returns.refundAmount')}</span>
              <input
                min="0"
                step="0.01"
                type="number"
                value={refundAmount}
                onChange={(event) => {
                  setRefundAmount(event.target.value);
                  setProcessingValidationError(null);
                }}
              />
            </label>
            <label>
              <span>{t('returns.refundMethod')}</span>
              <select
                value={refundMethod}
                onChange={(event) => setRefundMethod(event.target.value)}
              >
                <option value="manual_cash">{t('returns.refundMethod.cash')}</option>
                <option value="manual_transfer">{t('returns.refundMethod.transfer')}</option>
                <option value="other">{t('returns.refundMethod.other')}</option>
              </select>
            </label>
          </div>
          <label>
            <span>{t('returns.refundComment')}</span>
            <textarea
              rows={3}
              value={refundComment}
              onChange={(event) => setRefundComment(event.target.value)}
            />
          </label>

          <div className="returns-processing__items">
            {returnRequest.items.map((item) => {
              const alreadyRestocked = itemRestockedQuantity(item);
              const remainingQuantity = itemRemainingRestockableQuantity(item);
              const restockQuantity = Number(restockQuantities[item.id] ?? 0);
              const disabled = !itemCanRestock(item);
              const checked = restockQuantity > 0;
              return (
                <article
                  className={`returns-processing-item${disabled ? ' is-disabled' : ''}`}
                  key={item.id}
                >
                  <div className="returns-processing-item__summary">
                    <div>
                      <strong>{item.product_name}</strong>
                      <small>{[item.sku, item.color, item.size].filter(Boolean).join(' В· ')}</small>
                    </div>
                    <span>{formatMoney(item.unit_price, language)}</span>
                  </div>
                  <div className="returns-processing-item__metrics">
                    <span>{t('returns.returnedQuantity')}: {item.quantity}</span>
                    <span>{t('returns.alreadyRestocked')}: {alreadyRestocked}</span>
                    <span>{t('returns.remainingRestockable')}: {remainingQuantity}</span>
                  </div>
                  <div className="returns-processing-item__controls">
                    <label className="returns-processing-check">
                      <input
                        checked={checked}
                        disabled={disabled || actionBusy}
                        type="checkbox"
                        onChange={(event) => setItemRestockChecked(item, event.target.checked)}
                      />
                      <span>{t('returns.restockItem')}</span>
                    </label>
                    <label>
                      <span>{t('returns.restockQuantity')}</span>
                      <input
                        disabled={disabled || !checked || actionBusy}
                        max={remainingQuantity}
                        min="0"
                        type="number"
                        value={restockQuantity}
                        onChange={(event) => (
                          setItemRestockQuantity(item, Number(event.target.value))
                        )}
                      />
                    </label>
                  </div>
                  {!item.product_variant_id ? (
                    <small className="muted-text">{t('returns.notRestockable')}</small>
                  ) : null}
                </article>
              );
            })}
          </div>

          <label className="returns-processing-check">
            <input
              checked={completeAfterProcessing}
              disabled={actionBusy}
              type="checkbox"
              onChange={(event) => setCompleteAfterProcessing(event.target.checked)}
            />
            <span>{t('returns.completeAfterProcessing')}</span>
          </label>
          <label>
            <span>{t('returns.processingComment')}</span>
            <textarea
              rows={3}
              value={processingComment}
              onChange={(event) => setProcessingComment(event.target.value)}
            />
          </label>
          {processingValidationError ? (
            <p className="form-error">{processingValidationError}</p>
          ) : null}
          <button className="button button-primary" disabled={actionBusy} type="submit">
            {completeAfterProcessing ? t('returns.finishProcessing') : t('returns.saveProcessing')}
          </button>
        </form>
      ) : null}

      {returnRequest.status === 'PENDING' ? (
        <div className="returns-detail__actions">
          <button
            className="button button-primary"
            disabled={actionBusy}
            type="button"
            onClick={onApprove}
          >
            {t('returns.approve')}
          </button>
          <button
            className="button button-danger"
            disabled={actionBusy}
            type="button"
            onClick={onReject}
          >
            {t('returns.reject')}
          </button>
          <button
            className="button button-secondary"
            disabled={actionBusy}
            type="button"
            onClick={onCancel}
          >
            {t('returns.cancel')}
          </button>
        </div>
      ) : null}

      {returnRequest.status === 'APPROVED' ? (
        <div className="returns-detail__actions">
          <button
            className="button button-primary"
            disabled={actionBusy}
            type="button"
            onClick={onComplete}
          >
            {t('returns.complete')}
          </button>
          <button
            className="button button-secondary"
            disabled={actionBusy}
            type="button"
            onClick={onCancel}
          >
            {t('returns.cancel')}
          </button>
        </div>
      ) : null}

      {returnRequest.decided_at || returnRequest.decided_by_user_id || returnRequest.decision_comment ? (
        <dl className="details-list">
          <div><dt>{t('returns.decidedAt')}</dt><dd>{formatDate(returnRequest.decided_at, language)}</dd></div>
          <div><dt>{t('returns.decidedBy')}</dt><dd>{returnRequest.decided_by_user_id ?? t('common.notProvided')}</dd></div>
          <div><dt>{t('returns.decisionComment')}</dt><dd>{compactText(returnRequest.decision_comment, t('common.notProvided'))}</dd></div>
        </dl>
      ) : null}

      {returnRequest.completed_at || returnRequest.completed_by_user_id || returnRequest.completion_comment ? (
        <dl className="details-list">
          <div><dt>{t('returns.completedAt')}</dt><dd>{formatDate(returnRequest.completed_at, language)}</dd></div>
          <div><dt>{t('returns.completedBy')}</dt><dd>{returnRequest.completed_by_user_id ?? t('common.notProvided')}</dd></div>
          <div><dt>{t('returns.completionComment')}</dt><dd>{compactText(returnRequest.completion_comment, t('common.notProvided'))}</dd></div>
        </dl>
      ) : null}

      {returnRequest.cancelled_at || returnRequest.cancelled_by_user_id || returnRequest.cancellation_comment ? (
        <dl className="details-list">
          <div><dt>{t('returns.cancelledAt')}</dt><dd>{formatDate(returnRequest.cancelled_at, language)}</dd></div>
          <div><dt>{t('returns.cancelledBy')}</dt><dd>{returnRequest.cancelled_by_user_id ?? t('common.notProvided')}</dd></div>
          <div><dt>{t('returns.cancellationComment')}</dt><dd>{compactText(returnRequest.cancellation_comment, t('common.notProvided'))}</dd></div>
        </dl>
      ) : null}

      {returnRequest.refund ? (
        <dl className="details-list">
          <div><dt>{t('returns.refundAudit')}</dt><dd>{formatMoney(returnRequest.refund.amount, language)} {returnRequest.refund.currency}</dd></div>
          <div><dt>{t('returns.refundMethod')}</dt><dd>{compactText(returnRequest.refund.method, t('common.notProvided'))}</dd></div>
          <div><dt>{t('returns.refundComment')}</dt><dd>{compactText(returnRequest.refund.comment, t('common.notProvided'))}</dd></div>
          <div><dt>{t('returns.refundProcessedAt')}</dt><dd>{formatDate(returnRequest.refund.processed_at, language)}</dd></div>
          <div><dt>{t('returns.refundProcessedBy')}</dt><dd>{returnRequest.refund.processed_by_user_id ?? t('common.notProvided')}</dd></div>
        </dl>
      ) : null}

      {hasRestockAudit ? (
        <div className="returns-restock-audit">
          <h3>{t('returns.restockAudit')}</h3>
          {returnRequest.items.map((item) => (
            itemRestockedQuantity(item) > 0 ? (
              <div className="returns-restock-audit__row" key={item.id}>
                <span>{item.product_name}</span>
                <strong>{itemRestockedQuantity(item)} / {item.quantity}</strong>
              </div>
            ) : null
          ))}
        </div>
      ) : null}

      {actionError ? <p className="form-error">{actionError}</p> : null}
    </aside>
  );
}

function returnStatusLabel(status: ReturnRequestStatus, language: 'ru' | 'en'): string {
  return returnStatusLabels[language][status];
}

function toMoneyInputValue(value: unknown): string {
  const amount = Number(value ?? 0);
  return Number.isFinite(amount) ? amount.toFixed(2) : '0.00';
}

function parseMoneyInput(value: string): number | null {
  const normalized = value.trim().replace(',', '.');
  if (!normalized) {
    return null;
  }
  const amount = Number(normalized);
  return Number.isFinite(amount) ? amount : null;
}

function calculateReturnTotal(returnRequest: ReturnRequest | null): number {
  if (!returnRequest) {
    return 0;
  }
  return returnRequest.items.reduce(
    (total, item) => total + Number(item.unit_price ?? 0) * item.quantity,
    0,
  );
}

function itemRestockedQuantity(item: ReturnRequestItem): number {
  const quantity = Number(item.restocked_quantity ?? 0);
  return Number.isFinite(quantity) ? quantity : 0;
}

function itemRemainingRestockableQuantity(item: ReturnRequestItem): number {
  if (!item.product_variant_id) {
    return 0;
  }
  const remaining = Number(
    item.remaining_restockable_quantity
      ?? Math.max(item.quantity - itemRestockedQuantity(item), 0),
  );
  return Number.isFinite(remaining) ? Math.max(remaining, 0) : 0;
}

function itemCanRestock(item: ReturnRequestItem): boolean {
  return Boolean(item.product_variant_id) && itemRemainingRestockableQuantity(item) > 0;
}

function formatRequestError(error: unknown): string {
  if (error instanceof ApiError) {
    return error.message;
  }
  return error instanceof Error ? error.message : 'Request failed';
}
