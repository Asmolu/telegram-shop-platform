import { useEffect, useState } from 'react';
import { api } from '../../shared/api';
import type { AnalyticsSummary, Order, Product, PromoCode, Review } from '../../shared/api';
import { formatMoney } from '../../shared/utils/format';
import { EmptyState, ErrorState, LoadingState } from '../../shared/ui/DataState';
import { useI18n } from '../../shared/i18n';

interface DashboardData {
  products: Product[];
  orders: Order[];
  promoCodes: PromoCode[];
  pendingReviews: Review[];
  analytics: AnalyticsSummary | null;
}

interface PageProps {
  onNavigate: (path: string) => void;
  onAuthExpired: () => void;
}

export function DashboardPage({ onNavigate, onAuthExpired }: PageProps) {
  const { language, t } = useI18n();
  const [data, setData] = useState<DashboardData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<unknown>(null);

  function loadDashboard() {
    setLoading(true);
    setError(null);

    Promise.all([
      api.products.listAdmin({ limit: 100, offset: 0 }),
      api.orders.listAdmin({ limit: 100, offset: 0 }),
      api.promoCodes.list({ limit: 100, offset: 0 }),
      api.reviews.listAdmin('PENDING'),
      api.analytics.summary().catch(() => null),
    ])
      .then(([products, orders, promoCodes, pendingReviews, analytics]) => {
        setData({
          products: products.items,
          orders: orders.items,
          promoCodes: promoCodes.items,
          pendingReviews: pendingReviews.items,
          analytics,
        });
      })
      .catch(setError)
      .finally(() => setLoading(false));
  }

  useEffect(() => {
    loadDashboard();
  }, []);

  if (loading) return <LoadingState title={t('nav.dashboard')} />;
  if (error) {
    return <ErrorState error={error} onRetry={loadDashboard} onAuthExpired={onAuthExpired} />;
  }
  if (!data) {
    return (
      <EmptyState
        title={t('dashboard.noData')}
        description={t('dashboard.noDataDescription')}
      />
    );
  }

  const activeProducts = data.products.filter((product) => product.status === 'ACTIVE').length;
  const outOfStockProducts = data.products.filter(
    (product) => product.status === 'OUT_OF_STOCK',
  ).length;
  const newOrders = data.orders.filter((order) => order.status === 'NEW').length;
  const activePromoCodes = data.promoCodes.filter((promoCode) => promoCode.is_active).length;

  return (
    <div className="page-stack">
      <section className="kpi-grid">
        <KpiCard label={t('dashboard.activeProducts')} value={activeProducts} />
        <KpiCard label={t('dashboard.outOfStock')} value={outOfStockProducts} tone="warning" />
        <KpiCard label={t('dashboard.newOrders')} value={newOrders} tone="info" />
        <KpiCard label={t('dashboard.activePromoCodes')} value={activePromoCodes} />
        <KpiCard label={t('dashboard.pendingReviews')} value={data.pendingReviews.length} tone="warning" />
        <KpiCard
          label={t('dashboard.revenueTracked')}
          value={formatMoney(data.analytics?.total_revenue ?? 0, language)}
          tone="strong"
        />
      </section>

      <section className="widget-grid">
        <DashboardLink
          title={t('nav.products')}
          description={t('dashboard.productsDescription')}
          onClick={() => onNavigate('/products')}
        />
        <DashboardLink
          title={t('nav.orders')}
          description={t('dashboard.ordersDescription')}
          onClick={() => onNavigate('/orders')}
        />
        <DashboardLink
          title={t('nav.categoriesTags')}
          description={t('dashboard.taxonomyDescription')}
          onClick={() => onNavigate('/taxonomy')}
        />
        <DashboardLink
          title={t('nav.banners')}
          description={t('dashboard.bannersDescription')}
          onClick={() => onNavigate('/banners')}
        />
        <DashboardLink
          title={t('nav.promoCodes')}
          description={t('dashboard.promoDescription')}
          onClick={() => onNavigate('/promo-codes')}
        />
        <DashboardLink
          title={t('nav.reviews')}
          description={t('dashboard.reviewsDescription')}
          onClick={() => onNavigate('/reviews')}
        />
        <DashboardLink
          title={t('nav.statistics')}
          description={t('dashboard.statisticsDescription')}
          onClick={() => onNavigate('/statistics')}
        />
      </section>
    </div>
  );
}

function KpiCard({
  label,
  value,
  tone = 'default',
}: {
  label: string;
  value: string | number;
  tone?: 'default' | 'warning' | 'info' | 'strong';
}) {
  return (
    <article className={`kpi-card kpi-${tone}`}>
      <span>{label}</span>
      <strong>{value}</strong>
    </article>
  );
}

function DashboardLink({
  title,
  description,
  onClick,
}: {
  title: string;
  description: string;
  onClick: () => void;
}) {
  const { t } = useI18n();

  return (
    <button className="dashboard-link" type="button" onClick={onClick}>
      <span>{title}</span>
      <p>{description}</p>
      <strong>{t('common.open')}</strong>
    </button>
  );
}
