import { FormEvent, useEffect, useState } from 'react';
import { api } from '../../shared/api';
import type { AnalyticsEvent, AnalyticsSummary } from '../../shared/api';
import { ErrorState, LoadingState } from '../../shared/ui/DataState';
import { formatDate, formatMoney, fromDateTimeInput } from '../../shared/utils/format';

interface PageProps {
  onAuthExpired: () => void;
}

interface DateRange {
  from: string;
  to: string;
}

const initialRange: DateRange = { from: '', to: '' };

export function StatisticsPage({ onAuthExpired }: PageProps) {
  const [range, setRange] = useState<DateRange>(initialRange);
  const [draftRange, setDraftRange] = useState<DateRange>(initialRange);
  const [summary, setSummary] = useState<AnalyticsSummary | null>(null);
  const [events, setEvents] = useState<AnalyticsEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<unknown>(null);

  function loadStatistics() {
    setLoading(true);
    setError(null);

    const query = {
      created_from: fromDateTimeInput(range.from),
      created_to: fromDateTimeInput(range.to),
    };

    Promise.all([
      api.analytics.summary(query),
      api.analytics.events({ ...query, limit: 100, offset: 0 }),
    ])
      .then(([analyticsSummary, eventList]) => {
        setSummary(analyticsSummary);
        setEvents(eventList.items);
      })
      .catch(setError)
      .finally(() => setLoading(false));
  }

  useEffect(() => {
    loadStatistics();
  }, [range]);

  function applyRange(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setRange(draftRange);
  }

  if (loading) return <LoadingState title="Loading statistics" />;
  if (error) {
    return <ErrorState error={error} onRetry={loadStatistics} onAuthExpired={onAuthExpired} />;
  }

  return (
    <div className="page-stack">
      <form className="page-toolbar filters-row" onSubmit={applyRange}>
        <label>
          <span>From</span>
          <input
            type="datetime-local"
            value={draftRange.from}
            onChange={(event) => setDraftRange((current) => ({ ...current, from: event.target.value }))}
          />
        </label>
        <label>
          <span>To</span>
          <input
            type="datetime-local"
            value={draftRange.to}
            onChange={(event) => setDraftRange((current) => ({ ...current, to: event.target.value }))}
          />
        </label>
        <button className="button button-secondary" type="submit">
          Apply
        </button>
      </form>

      <section className="kpi-grid">
        <Kpi label="Product views" value={summary?.product_views_count ?? 0} />
        <Kpi label="Cart item added" value={summary?.cart_item_added_count ?? 0} />
        <Kpi label="Checkout started" value={summary?.checkout_started_count ?? 0} />
        <Kpi label="Orders created" value={summary?.total_orders ?? 0} />
        <Kpi label="Promo used" value={summary?.promo_used_count ?? 0} />
        <Kpi label="Revenue" value={formatMoney(summary?.total_revenue ?? 0)} />
      </section>

      <div className="split-view">
        <section className="table-panel">
          <div className="section-heading table-heading">
            <h2>Top products</h2>
          </div>
          <table>
            <thead>
              <tr>
                <th>Product</th>
                <th>Views</th>
              </tr>
            </thead>
            <tbody>
              {(summary?.top_products ?? []).length === 0 ? (
                <tr>
                  <td colSpan={2}>
                    <div className="empty-table">No top-product data yet.</div>
                  </td>
                </tr>
              ) : (
                summary?.top_products.map((product) => (
                  <tr key={product.product_id}>
                    <td>
                      <strong>{product.product_name ?? `Product ${product.product_id}`}</strong>
                      <small>ID {product.product_id}</small>
                    </td>
                    <td>{product.view_count}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </section>

        <section className="table-panel">
          <div className="section-heading table-heading">
            <h2>Recent events</h2>
          </div>
          <table>
            <thead>
              <tr>
                <th>Event</th>
                <th>User</th>
                <th>References</th>
                <th>Timestamp</th>
              </tr>
            </thead>
            <tbody>
              {events.length === 0 ? (
                <tr>
                  <td colSpan={4}>
                    <div className="empty-table">No analytics events in this range.</div>
                  </td>
                </tr>
              ) : (
                events.map((event) => (
                  <tr key={event.id}>
                    <td>{event.event_name}</td>
                    <td>{event.user_id ?? 'Anonymous'}</td>
                    <td>
                      <small>Product {event.product_id ?? '-'}</small>
                      <small>Order {event.order_id ?? '-'}</small>
                      <small>Promo {event.promo_code_id ?? '-'}</small>
                    </td>
                    <td>{formatDate(event.created_at)}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </section>
      </div>
    </div>
  );
}

function Kpi({ label, value }: { label: string; value: string | number }) {
  return (
    <article className="kpi-card">
      <span>{label}</span>
      <strong>{value}</strong>
    </article>
  );
}
