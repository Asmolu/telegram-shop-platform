import { useEffect, useMemo, useState } from 'react';
import { ApiError, api } from './shared/api';
import type { User } from './shared/api';
import { clearStoredToken, getStoredToken } from './shared/auth/tokenStorage';
import { AppShell, type NavItem } from './shared/ui/AppShell';
import { LoadingState } from './shared/ui/DataState';
import { DashboardPage } from './pages/Dashboard/DashboardPage';
import { SellerAuthPage } from './pages/Login/SellerAuthPage';
import { OrdersPage } from './pages/Orders/OrdersPage';
import { ProductsPage } from './pages/Products/ProductsPage';
import { ProductEditorPage } from './pages/ProductEditor/ProductEditorPage';
import { BannersPage } from './pages/Banners/BannersPage';
import { PromoCodesPage } from './pages/PromoCodes/PromoCodesPage';
import { ReviewsPage } from './pages/Reviews/ReviewsPage';
import { StatisticsPage } from './pages/Statistics/StatisticsPage';
import { SellerBotPage } from './pages/SellerBot/SellerBotPage';
import { SettingsPage } from './pages/Settings/SettingsPage';

const navItems: NavItem[] = [
  { path: '/dashboard', label: 'Dashboard' },
  { path: '/orders', label: 'Orders' },
  { path: '/products', label: 'Products' },
  { path: '/products/new', label: 'Add Product' },
  { path: '/banners', label: 'Banners' },
  { path: '/promo-codes', label: 'Promo Codes' },
  { path: '/reviews', label: 'Reviews' },
  { path: '/statistics', label: 'Statistics' },
  { path: '/seller-bot', label: 'Seller Bot' },
  { path: '/settings', label: 'Settings' },
];

function normalizePath(pathname: string): string {
  if (pathname === '/' || pathname === '') {
    return '/dashboard';
  }

  return pathname;
}

function getPageTitle(path: string): string {
  if (path.startsWith('/orders')) return 'Orders';
  if (path === '/products/new') return 'Add Product';
  if (path.startsWith('/products/') && path.endsWith('/edit')) return 'Edit Product';
  if (path.startsWith('/products')) return 'Products';
  if (path.startsWith('/banners')) return 'Banners';
  if (path.startsWith('/promo-codes')) return 'Promo Codes';
  if (path.startsWith('/reviews')) return 'Reviews';
  if (path.startsWith('/statistics')) return 'Statistics';
  if (path.startsWith('/seller-bot')) return 'Seller Bot';
  if (path.startsWith('/settings')) return 'Settings';
  return 'Dashboard';
}

export function App() {
  const [path, setPath] = useState(() => normalizePath(window.location.pathname));
  const [token, setToken] = useState(() => getStoredToken());
  const [user, setUser] = useState<User | null>(null);
  const [checkingUser, setCheckingUser] = useState(Boolean(token));
  const [authError, setAuthError] = useState<string | null>(null);

  const title = useMemo(() => getPageTitle(path), [path]);

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
        setAuthError(error instanceof Error ? error.message : 'Could not verify the token.');
      })
      .finally(() => {
        if (!cancelled) {
          setCheckingUser(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [token]);

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
        <LoadingState title="Checking seller token" />
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
  if (path === '/statistics') return <StatisticsPage {...sharedPageProps} />;
  if (path === '/seller-bot') return <SellerBotPage {...sharedPageProps} />;
  if (path === '/settings') return <SettingsPage {...sharedPageProps} />;

  return <DashboardPage {...sharedPageProps} />;
}
