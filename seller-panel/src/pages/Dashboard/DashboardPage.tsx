import { useEffect, useState, type ReactNode } from 'react';
import { api } from '../../shared/api';
import type { ApiDecimal, DashboardSummary } from '../../shared/api';
import { EmptyState, ErrorState, LoadingState } from '../../shared/ui/DataState';

interface PageProps {
  onNavigate: (path: string) => void;
  onAuthExpired: () => void;
}

export function DashboardPage({ onNavigate, onAuthExpired }: PageProps) {
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<unknown>(null);

  function loadDashboard() {
    setLoading(true);
    setError(null);

    api.dashboard
      .summary()
      .then(setSummary)
      .catch(setError)
      .finally(() => setLoading(false));
  }

  useEffect(() => {
    loadDashboard();
  }, []);

  if (loading) return <LoadingState title="Дашборд" />;
  if (error) {
    return <ErrorState error={error} onRetry={loadDashboard} onAuthExpired={onAuthExpired} />;
  }
  if (!summary) {
    return (
      <EmptyState
        title="Нет данных дашборда"
        description="Backend не вернул сводку по панели продавца."
      />
    );
  }

  const isEmptyDashboard =
    summary.active_orders_count === 0 &&
    summary.active_banners_count === 0 &&
    summary.products_total === 0 &&
    summary.products_out_of_stock === 0 &&
    Number(summary.revenue_month.net_revenue) === 0;

  return (
    <div className="page-stack">
      <section className="kpi-grid">
        <KpiCard
          label="Активные заказы"
          value={formatInteger(summary.active_orders_count)}
          tone="info"
        />
        <KpiCard
          label="Активные баннеры"
          value={formatInteger(summary.active_banners_count)}
        />
        <KpiCard label="Всего товаров" value={formatInteger(summary.products_total)} />
        <KpiCard
          label="Товары закончились"
          value={formatInteger(summary.products_out_of_stock)}
          tone="warning"
        />
        <KpiCard
          label="Выручка за месяц"
          value={formatRubles(summary.revenue_month.net_revenue)}
          subtitle={formatMonthLabel(summary.revenue_month.period_start)}
          tone="strong"
          wide
        >
          <div className="kpi-breakdown-row">
            <span>Заказов</span>
            <strong>{formatInteger(summary.revenue_month.orders_count)}</strong>
          </div>
          <div className="kpi-breakdown-row">
            <span>До скидок</span>
            <strong>{formatRubles(summary.revenue_month.gross_revenue)}</strong>
          </div>
          <div className="kpi-breakdown-row">
            <span>Скидки</span>
            <strong>{formatRubles(summary.revenue_month.discount_total)}</strong>
          </div>
        </KpiCard>
      </section>

      {isEmptyDashboard ? (
        <EmptyState
          title="Пока нет данных для дашборда"
          description="Когда появятся товары, заказы или активные баннеры, сводка заполнится автоматически."
        />
      ) : null}

      <section className="widget-grid">
        <DashboardLink
          title="Товары"
          description="Каталог, остатки, варианты, статусы и изображения."
          onClick={() => onNavigate('/products')}
        />
        <DashboardLink
          title="Заказы"
          description="Активные заказы, ручная оплата и статусы исполнения."
          onClick={() => onNavigate('/orders')}
        />
        <DashboardLink
          title="Категории и теги"
          description="Структура каталога и быстрые метки товаров."
          onClick={() => onNavigate('/taxonomy')}
        />
        <DashboardLink
          title="Баннеры"
          description="Видимые баннеры Mini App, форматы и цели перехода."
          onClick={() => onNavigate('/banners')}
        />
        <DashboardLink
          title="Промокоды"
          description="Скидки, лимиты использования и сроки активности."
          onClick={() => onNavigate('/promo-codes')}
        />
        <DashboardLink
          title="Отзывы"
          description="Модерация отзывов покупателей после покупки."
          onClick={() => onNavigate('/reviews')}
        />
        <DashboardLink
          title="Статистика"
          description="События, топы товаров, промокодов и баннеров."
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
  subtitle,
  wide = false,
  children,
}: {
  label: string;
  value: string | number;
  tone?: 'default' | 'warning' | 'info' | 'strong';
  subtitle?: string;
  wide?: boolean;
  children?: ReactNode;
}) {
  return (
    <article className={`kpi-card kpi-${tone}${wide ? ' kpi-wide' : ''}`}>
      <span>{label}</span>
      <strong>{value}</strong>
      {subtitle ? <small className="kpi-subtitle">{subtitle}</small> : null}
      {children ? <div className="kpi-breakdown">{children}</div> : null}
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
      <strong>Открыть</strong>
    </button>
  );
}

function formatInteger(value: number): string {
  return new Intl.NumberFormat('ru-RU').format(value);
}

function formatRubles(value: ApiDecimal | null | undefined): string {
  const amount = Number(value ?? 0);
  return new Intl.NumberFormat('ru-RU', {
    style: 'currency',
    currency: 'RUB',
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(Number.isFinite(amount) ? amount : 0);
}

function formatMonthLabel(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return 'Текущий месяц';
  }

  const label = new Intl.DateTimeFormat('ru-RU', {
    month: 'long',
    year: 'numeric',
    timeZone: 'Europe/Moscow',
  }).format(date);
  return `${label.charAt(0).toUpperCase()}${label.slice(1)}`;
}
