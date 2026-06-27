import { FormEvent, useEffect, useState } from 'react';
import { api } from '../../shared/api';
import type { AnalyticsEvent, AnalyticsSummary } from '../../shared/api';
import { useI18n } from '../../shared/i18n';
import { ErrorState, LoadingState } from '../../shared/ui/DataState';
import { formatDate, formatMoney, fromDateTimeInput } from '../../shared/utils/format';

interface PageProps {
  onAuthExpired: () => void;
}

interface DateRange {
  from: string;
  to: string;
}

type EventFilter = 'all' | 'product' | 'promo' | 'banner';

const initialRange: DateRange = { from: '', to: '' };

export function StatisticsPage({ onAuthExpired }: PageProps) {
  const { language, t } = useI18n();
  const [range, setRange] = useState<DateRange>(initialRange);
  const [draftRange, setDraftRange] = useState<DateRange>(initialRange);
  const [eventFilter, setEventFilter] = useState<EventFilter>('all');
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
      api.analytics.events({
        ...query,
        event_name: eventNameForFilter(eventFilter),
        limit: 100,
        offset: 0,
      }),
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
  }, [range, eventFilter]);

  function applyRange(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setRange(draftRange);
  }

  if (loading) return <LoadingState title={t('statistics.loading')} />;
  if (error) {
    return <ErrorState error={error} onRetry={loadStatistics} onAuthExpired={onAuthExpired} />;
  }

  return (
    <div className="page-stack">
      <form className="page-toolbar filters-row" onSubmit={applyRange}>
        <label>
          <span>{t('common.from')}</span>
          <input
            type="datetime-local"
            value={draftRange.from}
            onChange={(event) => setDraftRange((current) => ({ ...current, from: event.target.value }))}
          />
        </label>
        <label>
          <span>{t('common.to')}</span>
          <input
            type="datetime-local"
            value={draftRange.to}
            onChange={(event) => setDraftRange((current) => ({ ...current, to: event.target.value }))}
          />
        </label>
        <label>
          <span>{t('statistics.eventFilter')}</span>
          <select
            value={eventFilter}
            onChange={(event) => setEventFilter(event.target.value as EventFilter)}
          >
            <option value="all">{t('statistics.allEvents')}</option>
            <option value="product">{t('statistics.productInteractions')}</option>
            <option value="promo">{t('statistics.promoInteractions')}</option>
            <option value="banner">{t('statistics.bannerInteractions')}</option>
          </select>
        </label>
        <button className="button button-secondary" type="submit">
          {t('common.apply')}
        </button>
      </form>

      <section className="kpi-grid">
        <Kpi label={t('statistics.productViews')} value={summary?.product_views_count ?? 0} />
        <Kpi label={t('statistics.cartAdds')} value={summary?.cart_item_added_count ?? 0} />
        <Kpi label={t('statistics.checkoutStarted')} value={summary?.checkout_started_count ?? 0} />
        <Kpi label={t('statistics.ordersCreated')} value={summary?.order_created_count ?? summary?.total_orders ?? 0} />
        <Kpi label={t('statistics.promoUsed')} value={summary?.promo_used_count ?? 0} />
        <Kpi label={t('statistics.bannerClicks')} value={summary?.banner_clicked_count ?? 0} />
        <Kpi label={t('statistics.revenue')} value={formatMoney(summary?.total_revenue ?? 0, language)} />
      </section>

      <div className="panel muted-text statistics-gap-note">{t('statistics.apiGap')}</div>

      <div className="analytics-grid">
        <section className="table-panel">
          <div className="section-heading table-heading">
            <h2>{t('statistics.topProducts')}</h2>
          </div>
          <table>
            <thead>
              <tr>
                <th>{t('common.product')}</th>
                <th>{t('statistics.views')}</th>
              </tr>
            </thead>
            <tbody>
              {(summary?.top_products ?? []).length === 0 ? (
                <tr>
                  <td colSpan={2}>
                    <div className="empty-table">{t('statistics.noTopProducts')}</div>
                  </td>
                </tr>
              ) : (
                summary?.top_products.map((product) => (
                  <tr key={product.product_id}>
                    <td>
                      <strong>{product.product_name ?? `${t('common.product')} ${product.product_id}`}</strong>
                      <small>{t('common.id')} {product.product_id}</small>
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
            <h2>{t('statistics.topPromos')}</h2>
          </div>
          <table>
            <thead>
              <tr>
                <th>{t('orders.promoCode')}</th>
                <th>{t('statistics.uses')}</th>
              </tr>
            </thead>
            <tbody>
              {(summary?.top_promo_codes ?? []).length === 0 ? (
                <tr>
                  <td colSpan={2}>
                    <div className="empty-table">{t('statistics.noTopPromos')}</div>
                  </td>
                </tr>
              ) : (
                summary?.top_promo_codes?.map((promo) => (
                  <tr key={promo.promo_code_id}>
                    <td>
                      <strong>{promo.promo_code ?? `${t('orders.promoCode')} ${promo.promo_code_id}`}</strong>
                      <small>{t('common.id')} {promo.promo_code_id}</small>
                    </td>
                    <td>{promo.used_count}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </section>

        <section className="table-panel">
          <div className="section-heading table-heading">
            <h2>{t('statistics.topBanners')}</h2>
          </div>
          <table>
            <thead>
              <tr>
                <th>{t('common.banner')}</th>
                <th>{t('statistics.clicks')}</th>
              </tr>
            </thead>
            <tbody>
              {(summary?.top_banners ?? []).length === 0 ? (
                <tr>
                  <td colSpan={2}>
                    <div className="empty-table">{t('statistics.noTopBanners')}</div>
                  </td>
                </tr>
              ) : (
                summary?.top_banners?.map((banner) => (
                  <tr key={banner.banner_id}>
                    <td>
                      <strong>{banner.banner_title ?? `${t('common.banner')} ${banner.banner_id}`}</strong>
                      <small>{t('common.id')} {banner.banner_id}</small>
                    </td>
                    <td>{banner.click_count}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </section>
      </div>

      <section className="table-panel">
        <div className="section-heading table-heading">
          <h2>{t('statistics.recentEvents')}</h2>
        </div>
        <table>
          <thead>
            <tr>
              <th>{t('common.event')}</th>
              <th>{t('common.user')}</th>
              <th>{t('statistics.references')}</th>
              <th>{t('statistics.timestamp')}</th>
            </tr>
          </thead>
          <tbody>
            {events.length === 0 ? (
              <tr>
                <td colSpan={4}>
                  <div className="empty-table">{t('statistics.noEvents')}</div>
                </td>
              </tr>
            ) : (
              events.map((event) => (
                <tr key={event.id}>
                  <td>{event.event_name}</td>
                  <td>{formatAnalyticsUserLabel(event, t('common.anonymous'))}</td>
                  <td>
                    <small>{t('common.product')} {event.product_id ?? '-'}</small>
                    <small>{t('orders.order')} {event.order_id ?? '-'}</small>
                    <small>{t('orders.promoCode')} {event.promo_code_id ?? '-'}</small>
                    <small>{t('common.banner')} {event.banner_id ?? '-'}</small>
                  </td>
                  <td>{formatDate(event.created_at, language)}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </section>
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

export function formatAnalyticsUserLabel(event: Pick<AnalyticsEvent, 'user_id'>, anonymousLabel: string) {
  return event.user_id === null ? anonymousLabel : `ID ${event.user_id}`;
}

function eventNameForFilter(filter: EventFilter): string | undefined {
  if (filter === 'product') return 'product.viewed';
  if (filter === 'promo') return 'promo.used';
  if (filter === 'banner') return 'banner.clicked';
  return undefined;
}
