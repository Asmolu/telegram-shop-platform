import { useEffect, useMemo, useState } from 'react';
import { ApiError, api, resolveMediaUrl } from '../../shared/api';
import type { ReturnRequest, ReturnRequestStatus } from '../../shared/api';
import { labelForEnum, useI18n } from '../../shared/i18n';
import { ErrorState, LoadingState } from '../../shared/ui/DataState';
import { StatusBadge } from '../../shared/ui/StatusBadge';
import { compactText, formatDate, formatMoney } from '../../shared/utils/format';

interface PageProps {
  initialReturnRequestId?: number;
  onNavigate: (path: string) => void;
  onAuthExpired: () => void;
}

const returnStatuses: ReturnRequestStatus[] = ['PENDING', 'APPROVED', 'REJECTED'];

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

  async function decideReturn(nextStatus: Exclude<ReturnRequestStatus, 'PENDING'>) {
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
      setSelectedReturn(updated);
      setReturnRequests((current) => (
        current.map((request) => (request.id === updated.id ? updated : request))
      ));
      setNotice(t('returns.decisionSaved', {
        number: updated.return_number,
        status: labelForEnum(updated.status, t).toLowerCase(),
      }));
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
                {labelForEnum(status, t)}
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
                      <td><StatusBadge status={returnRequest.status} /></td>
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
  onReject,
  onOpenOrder,
  returnRequest,
}: {
  actionBusy: boolean;
  actionError: string | null;
  detailLoading: boolean;
  onApprove: () => void;
  onReject: () => void;
  onOpenOrder: () => void;
  returnRequest: ReturnRequest | null;
}) {
  const { language, t } = useI18n();

  if (detailLoading) {
    return <div className="detail-drawer"><LoadingState title={t('returns.detailLoading')} /></div>;
  }
  if (!returnRequest) {
    return <div className="detail-drawer empty-drawer">{t('returns.selectRequest')}</div>;
  }

  return (
    <aside className="detail-drawer returns-detail">
      <div className="returns-detail__header">
        <div>
          <h2>{returnRequest.return_number}</h2>
          <p>{t('orders.order')} {returnRequest.order_number ?? `#${returnRequest.order_id}`}</p>
        </div>
        <StatusBadge status={returnRequest.status} />
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
        </div>
      ) : (
        <dl className="details-list">
          <div><dt>{t('returns.decidedAt')}</dt><dd>{formatDate(returnRequest.decided_at, language)}</dd></div>
          <div><dt>{t('returns.decidedBy')}</dt><dd>{returnRequest.decided_by_user_id ?? t('common.notProvided')}</dd></div>
          <div><dt>{t('returns.decisionComment')}</dt><dd>{compactText(returnRequest.decision_comment, t('common.notProvided'))}</dd></div>
        </dl>
      )}

      {actionError ? <p className="form-error">{actionError}</p> : null}
    </aside>
  );
}

function formatRequestError(error: unknown): string {
  if (error instanceof ApiError) {
    return error.message;
  }
  return error instanceof Error ? error.message : 'Request failed';
}
