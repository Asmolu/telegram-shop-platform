import { useEffect, useMemo, useState } from 'react';
import { ApiError, api } from './shared/api';
import type { User } from './shared/api';
import { clearStoredToken, getStoredToken } from './shared/auth/tokenStorage';
import { useI18n } from './shared/i18n';
import { AppShell, type NavItem } from './shared/ui/AppShell';
import { LoadingState } from './shared/ui/DataState';
import { DashboardPage } from './pages/Dashboard/DashboardPage';
import { SellerAuthPage } from './pages/Login/SellerAuthPage';
import { OrdersPage } from './pages/Orders/OrdersPage';
import { ProductsPage } from './pages/Products/ProductsPage';
import { ProductEditorPage } from './pages/ProductEditor/ProductEditorPage';
import { TaxonomyPage } from './pages/Taxonomy/TaxonomyPage';
import { BannersPage } from './pages/Banners/BannersPage';
import { PromoCodesPage } from './pages/PromoCodes/PromoCodesPage';
import { ReviewsPage } from './pages/Reviews/ReviewsPage';
import { ReturnsPage } from './pages/Returns/ReturnsPage';
import { StatisticsPage } from './pages/Statistics/StatisticsPage';
import { SellerBotPage } from './pages/SellerBot/SellerBotPage';
import { CustomerNotificationsPage } from './pages/CustomerNotifications/CustomerNotificationsPage';
import { ChannelEntryPage } from './pages/ChannelEntry/ChannelEntryPage';
import { SettingsPage } from './pages/Settings/SettingsPage';

const navItems: NavItem[] = [
  { path: '/dashboard', labelKey: 'nav.dashboard' },
  { path: '/orders', labelKey: 'nav.orders' },
  { path: '/products', labelKey: 'nav.products' },
  { path: '/products/new', labelKey: 'nav.addProduct' },
  { path: '/taxonomy', labelKey: 'nav.categoriesTags' },
  { path: '/banners', labelKey: 'nav.banners' },
  { path: '/promo-codes', labelKey: 'nav.promoCodes' },
  { path: '/reviews', labelKey: 'nav.reviews' },
  { path: '/returns', labelKey: 'nav.returns' },
  { path: '/statistics', labelKey: 'nav.statistics' },
  { path: '/customer-notifications', labelKey: 'nav.customerNotifications' },
  { path: '/channel-entry', labelKey: 'nav.channelEntry' },
  { path: '/seller-bot', labelKey: 'nav.sellerBot' },
  { path: '/settings', labelKey: 'nav.settings' },
];

function normalizePath(pathname: string): string {
  if (pathname === '/' || pathname === '') {
    return '/dashboard';
  }

  return pathname;
}

function getPageTitleKey(path: string): string {
  if (path.startsWith('/orders')) return 'nav.orders';
  if (path === '/products/new') return 'nav.addProduct';
  if (path.startsWith('/products/') && path.endsWith('/edit')) return 'nav.editProduct';
  if (path.startsWith('/products')) return 'nav.products';
  if (path.startsWith('/taxonomy')) return 'nav.categoriesTags';
  if (path.startsWith('/banners')) return 'nav.banners';
  if (path.startsWith('/promo-codes')) return 'nav.promoCodes';
  if (path.startsWith('/reviews')) return 'nav.reviews';
  if (path.startsWith('/returns')) return 'nav.returns';
  if (path.startsWith('/statistics')) return 'nav.statistics';
  if (path.startsWith('/customer-notifications')) return 'nav.customerNotifications';
  if (path.startsWith('/channel-entry')) return 'nav.channelEntry';
  if (path.startsWith('/seller-bot')) return 'nav.sellerBot';
  if (path.startsWith('/settings')) return 'nav.settings';
  return 'nav.dashboard';
}

export function App() {
  const { t } = useI18n();
  const [path, setPath] = useState(() => normalizePath(window.location.pathname));
  const [token, setToken] = useState(() => getStoredToken());
  const [user, setUser] = useState<User | null>(null);
  const [checkingUser, setCheckingUser] = useState(Boolean(token));
  const [authError, setAuthError] = useState<string | null>(null);

  const title = useMemo(() => t(getPageTitleKey(path)), [path, t]);

  useEffect(() => {
    const onPopState = () => setPath(normalizePath(window.location.pathname));
    window.addEventListener('popstate', onPopState);
    return () => window.removeEventListener('popstate', onPopState);
  }, []);

  useEffect(() => {
    if (!token) {
      setCheckingUser(false);
      setUser(null);
      return;
    }

    let cancelled = false;
    setCheckingUser(true);
    setAuthError(null);

    api.sellerAuth
      .me()
      .then((currentUser) => {
        if (cancelled) return;
        setUser(currentUser);
      })
      .catch((error: unknown) => {
        if (cancelled) return;
        if (error instanceof ApiError && (error.status === 401 || error.status === 403)) {
          clearStoredToken();
          setToken(null);
          setUser(null);
          setAuthError(error.message);
          navigate('/login');
          return;
        }
        setAuthError(error instanceof Error ? error.message : t('app.tokenVerifyFailed'));
      })
      .finally(() => {
        if (!cancelled) {
          setCheckingUser(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [token, t]);

  function navigate(nextPath: string) {
    const normalized = normalizePath(nextPath);
    window.history.pushState(null, '', normalized);
    setPath(normalized);
  }

  function handleLogout() {
    clearStoredToken();
    setToken(null);
    setUser(null);
    navigate('/login');
  }

  function handleTokenSaved() {
    setToken(getStoredToken());
    navigate('/dashboard');
  }

  if (!token || path === '/login') {
    return <SellerAuthPage authError={authError} onTokenSaved={handleTokenSaved} />;
  }

  if (checkingUser) {
    return (
      <div className="auth-loading">
        <LoadingState title={t('app.checkingToken')} />
      </div>
    );
  }

  const sharedPageProps = {
    onNavigate: navigate,
    onAuthExpired: handleLogout,
  };

  return (
    <AppShell
      navItems={navItems}
      currentPath={path}
      title={title}
      user={user}
      onNavigate={navigate}
      onLogout={handleLogout}
    >
      {renderPage(path, sharedPageProps)}
    </AppShell>
  );
}

function renderPage(
  path: string,
  sharedPageProps: { onNavigate: (path: string) => void; onAuthExpired: () => void },
) {
  if (path === '/dashboard') return <DashboardPage {...sharedPageProps} />;
  if (path === '/orders') return <OrdersPage {...sharedPageProps} />;
  if (path === '/products') return <ProductsPage {...sharedPageProps} />;
  if (path === '/products/new') return <ProductEditorPage mode="create" {...sharedPageProps} />;
  if (path === '/taxonomy') return <TaxonomyPage {...sharedPageProps} />;

  const productEditMatch = path.match(/^\/products\/(\d+)\/edit$/);
  if (productEditMatch) {
    return (
      <ProductEditorPage
        mode="edit"
        productId={Number(productEditMatch[1])}
        {...sharedPageProps}
      />
    );
  }

  if (path === '/banners') return <BannersPage {...sharedPageProps} />;
  if (path === '/promo-codes') return <PromoCodesPage {...sharedPageProps} />;
  if (path === '/reviews') return <ReviewsPage {...sharedPageProps} />;
  if (path === '/returns' || /^\/returns\/\d+$/.test(path)) {
    const match = path.match(/^\/returns\/(\d+)$/);
    return (
      <ReturnsPage
        initialReturnRequestId={match ? Number(match[1]) : undefined}
        {...sharedPageProps}
      />
    );
  }
  if (path === '/statistics') return <StatisticsPage {...sharedPageProps} />;
  if (path === '/customer-notifications') return <CustomerNotificationsPage {...sharedPageProps} />;
  if (path === '/channel-entry') return <ChannelEntryPage {...sharedPageProps} />;
  if (path === '/seller-bot') return <SellerBotPage {...sharedPageProps} />;
  if (path === '/settings') return <SettingsPage {...sharedPageProps} />;

  return <DashboardPage {...sharedPageProps} />;
}
