import { FormEvent, useEffect, useMemo, useState } from 'react';
import { api } from '../../shared/api';
import type { CustomerNotificationSubscription, PageMeta } from '../../shared/api';
import { ErrorState, LoadingState } from '../../shared/ui/DataState';
import { formatDate } from '../../shared/utils/format';

interface PageProps {
  onAuthExpired: () => void;
}

type BooleanFilter = 'all' | 'true' | 'false';

const PAGE_LIMIT = 20;

export function CustomerNotificationsPage({ onAuthExpired }: PageProps) {
  const [items, setItems] = useState<CustomerNotificationSubscription[]>([]);
  const [meta, setMeta] = useState<PageMeta | undefined>();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<unknown>(null);
  const [offset, setOffset] = useState(0);
  const [hasChat, setHasChat] = useState<BooleanFilter>('all');
  const [serviceOptIn, setServiceOptIn] = useState<BooleanFilter>('all');
  const [marketingOptIn, setMarketingOptIn] = useState<BooleanFilter>('all');
  const [blocked, setBlocked] = useState<BooleanFilter>('all');
  const [userId, setUserId] = useState('');
  const [telegramUsername, setTelegramUsername] = useState('');

  const total = meta?.total ?? 0;
  const canGoBack = offset > 0;
  const canGoNext = total > offset + PAGE_LIMIT;

  const query = useMemo(
    () => ({
      limit: PAGE_LIMIT,
      offset,
      has_chat: filterValue(hasChat),
      service_opt_in: filterValue(serviceOptIn),
      marketing_opt_in: filterValue(marketingOptIn),
      blocked: filterValue(blocked),
      user_id: userId ? Number(userId) : undefined,
      telegram_username: telegramUsername.trim() || undefined,
    }),
    [blocked, hasChat, marketingOptIn, offset, serviceOptIn, telegramUsername, userId],
  );

  function loadSubscriptions() {
    setLoading(true);
    setError(null);
    api.customerNotifications
      .subscriptions(query)
      .then((response) => {
        setItems(response.items);
        setMeta(response.meta);
      })
      .catch((requestError) => setError(requestError))
      .finally(() => setLoading(false));
  }

  useEffect(() => {
    loadSubscriptions();
  }, [query]);

  function handleFiltersSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setOffset(0);
    loadSubscriptions();
  }

  if (loading) return <LoadingState title="Loading recipients" />;
  if (error) {
    return <ErrorState error={error} onRetry={loadSubscriptions} onAuthExpired={onAuthExpired} />;
  }

  return (
    <div className="page-stack">
      <section className="panel">
        <div className="section-heading">
          <div>
            <h2>Customer notification recipients</h2>
            <p>Bot 1 customer chat and consent registry. Campaign sending is not available here.</p>
          </div>
          <span className="status-badge status-info">{total} total</span>
        </div>

        <form className="filters-row customer-notification-filters" onSubmit={handleFiltersSubmit}>
          <label>
            <span>Has chat</span>
            <select value={hasChat} onChange={(event) => setHasChat(event.target.value as BooleanFilter)}>
              <option value="all">All</option>
              <option value="true">Connected</option>
              <option value="false">Missing</option>
            </select>
          </label>
          <label>
            <span>Service</span>
            <select
              value={serviceOptIn}
              onChange={(event) => setServiceOptIn(event.target.value as BooleanFilter)}
            >
              <option value="all">All</option>
              <option value="true">On</option>
              <option value="false">Off</option>
            </select>
          </label>
          <label>
            <span>Marketing</span>
            <select
              value={marketingOptIn}
              onChange={(event) => setMarketingOptIn(event.target.value as BooleanFilter)}
            >
              <option value="all">All</option>
              <option value="true">On</option>
              <option value="false">Off</option>
            </select>
          </label>
          <label>
            <span>Blocked</span>
            <select value={blocked} onChange={(event) => setBlocked(event.target.value as BooleanFilter)}>
              <option value="all">All</option>
              <option value="true">Blocked</option>
              <option value="false">Not blocked</option>
            </select>
          </label>
          <label>
            <span>User ID</span>
            <input
              min="1"
              placeholder="Any"
              type="number"
              value={userId}
              onChange={(event) => setUserId(event.target.value)}
            />
          </label>
          <label>
            <span>Telegram username</span>
            <input
              placeholder="@username"
              value={telegramUsername}
              onChange={(event) => setTelegramUsername(event.target.value)}
            />
          </label>
          <button className="button button-primary" type="submit">
            Apply
          </button>
        </form>
      </section>

      <section className="table-panel">
        <div className="section-heading table-heading">
          <h2>Recipients</h2>
          <div className="inline-actions">
            <button
              className="button button-secondary"
              disabled={!canGoBack}
              type="button"
              onClick={() => setOffset(Math.max(0, offset - PAGE_LIMIT))}
            >
              Previous
            </button>
            <button
              className="button button-secondary"
              disabled={!canGoNext}
              type="button"
              onClick={() => setOffset(offset + PAGE_LIMIT)}
            >
              Next
            </button>
            <button className="button button-secondary" type="button" onClick={loadSubscriptions}>
              Refresh
            </button>
          </div>
        </div>
        <table>
          <thead>
            <tr>
              <th>User</th>
              <th>Telegram</th>
              <th>Chat</th>
              <th>Service</th>
              <th>Marketing</th>
              <th>Blocked</th>
              <th>Last activity</th>
            </tr>
          </thead>
          <tbody>
            {items.length === 0 ? (
              <tr>
                <td colSpan={7}>
                  <div className="empty-table">No customer recipients match these filters.</div>
                </td>
              </tr>
            ) : (
              items.map((subscription) => (
                <tr key={subscription.id}>
                  <td>
                    <strong>{subscription.user_id ? `User ${subscription.user_id}` : 'Unlinked'}</strong>
                    <small>Subscription {subscription.id}</small>
                  </td>
                  <td>
                    <strong>{formatTelegramName(subscription)}</strong>
                    <small>Telegram user {subscription.telegram_user_id}</small>
                  </td>
                  <td>
                    <StatusBadge
                      className={subscription.has_chat ? 'status-success' : 'status-neutral'}
                      label={subscription.has_chat ? 'Connected' : 'Missing'}
                    />
                    <small>{subscription.telegram_chat_id_masked ?? '-'}</small>
                  </td>
                  <td>
                    <StatusBadge
                      className={subscription.service_opt_in ? 'status-success' : 'status-warning'}
                      label={subscription.service_opt_in ? 'On' : 'Off'}
                    />
                  </td>
                  <td>
                    <StatusBadge
                      className={subscription.marketing_opt_in ? 'status-info' : 'status-neutral'}
                      label={subscription.marketing_opt_in ? 'On' : 'Off'}
                    />
                  </td>
                  <td>
                    <StatusBadge
                      className={subscription.blocked_at ? 'status-danger' : 'status-success'}
                      label={subscription.blocked_at ? 'Blocked' : 'OK'}
                    />
                    {subscription.blocked_at ? <small>{formatDate(subscription.blocked_at)}</small> : null}
                  </td>
                  <td>
                    <small>Start: {formatOptionalDate(subscription.last_start_at)}</small>
                    <small>Stop: {formatOptionalDate(subscription.last_stop_at)}</small>
                    <small>Settings: {formatOptionalDate(subscription.last_settings_at)}</small>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </section>
    </div>
  );
}

function filterValue(value: BooleanFilter): boolean | undefined {
  if (value === 'all') {
    return undefined;
  }
  return value === 'true';
}

function formatTelegramName(subscription: CustomerNotificationSubscription): string {
  if (subscription.telegram_username) {
    return `@${subscription.telegram_username}`;
  }
  return [subscription.telegram_first_name, subscription.telegram_last_name].filter(Boolean).join(' ') || '-';
}

function formatOptionalDate(value: string | null): string {
  return value ? formatDate(value) : '-';
}

function StatusBadge({ className, label }: { className: string; label: string }) {
  return <span className={`status-badge ${className}`}>{label}</span>;
}
