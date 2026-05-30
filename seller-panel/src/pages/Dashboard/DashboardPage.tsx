import { useEffect, useState } from 'react';
import { api } from '../../shared/api';
import type { AnalyticsSummary, Order, Product, PromoCode, Review } from '../../shared/api';
import { formatMoney } from '../../shared/utils/format';
import { EmptyState, ErrorState, LoadingState } from '../../shared/ui/DataState';

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

  if (loading) return <LoadingState title="Loading dashboard" />;
  if (error) {
    return <ErrorState error={error} onRetry={loadDashboard} onAuthExpired={onAuthExpired} />;
  }
  if (!data) return <EmptyState title="No dashboard data" description="The API returned no data." />;

  const activeProducts = data.products.filter((product) => product.status === 'ACTIVE').length;
  const outOfStockProducts = data.products.filter(
    (product) => product.status === 'OUT_OF_STOCK',
  ).length;
  const newOrders = data.orders.filter((order) => order.status === 'NEW').length;
  const activePromoCodes = data.promoCodes.filter((promoCode) => promoCode.is_active).length;

  return (
    <div className="page-stack">
      <section className="kpi-grid">
        <KpiCard label="Active products" value={activeProducts} />
        <KpiCard label="Out of stock" value={outOfStockProducts} tone="warning" />
        <KpiCard label="New orders" value={newOrders} tone="info" />
        <KpiCard label="Active promo codes" value={activePromoCodes} />
        <KpiCard label="Pending reviews" value={data.pendingReviews.length} tone="warning" />
        <KpiCard
          label="Revenue tracked"
          value={formatMoney(data.analytics?.total_revenue ?? 0)}
          tone="strong"
        />
      </section>

      <section className="widget-grid">
        <DashboardLink
          title="Products"
          description="Manage catalog, stock, variants, status, and images."
          onClick={() => onNavigate('/products')}
        />
        <DashboardLink
          title="Orders"
          description="Review new orders and update fulfillment statuses."
          onClick={() => onNavigate('/orders')}
        />
        <DashboardLink
          title="Banners"
          description="Configure Mini App banner placements and destinations."
          onClick={() => onNavigate('/banners')}
        />
        <DashboardLink
          title="Promo Codes"
          description="Create, edit, and deactivate discount codes."
          onClick={() => onNavigate('/promo-codes')}
        />
        <DashboardLink
          title="Reviews"
          description="Moderate pending product reviews."
          onClick={() => onNavigate('/reviews')}
        />
        <DashboardLink
          title="Statistics"
          description="Inspect basic event reporting and top products."
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
  return (
    <button className="dashboard-link" type="button" onClick={onClick}>
      <span>{title}</span>
      <p>{description}</p>
      <strong>Open</strong>
    </button>
  );
}
