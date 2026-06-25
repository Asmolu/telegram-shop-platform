import React from 'react';
import { AuthProvider } from './shared/auth/AuthProvider';
import { NetworkProvider } from './shared/network/NetworkProvider';
import { RouterProvider, getRouteId, useRouter } from './shared/router/RouterProvider';
import { ChunkLoadRecovery } from './shared/router/ChunkLoadRecovery';
import { registerRoutePrefetchers } from './shared/router/routePrefetch';
import { ThemeProvider } from './shared/theme/ThemeProvider';
import { getConnectionTelemetry, getViewportTelemetry, normalizeRoute, trackTelemetry } from './shared/telemetry';
import { AppErrorBoundary } from './shared/ui/AppErrorBoundary';
import { AppShell, TopBar } from './shared/ui/AppShell';

const routeLoaders = {
  launch: () => import('./pages/LaunchPage').then((module) => ({ default: module.LaunchPage })),
  main: () => import('./pages/MainPage').then((module) => ({ default: module.MainPage })),
  categories: () => import('./pages/CategoriesPage').then((module) => ({ default: module.CategoriesPage })),
  'category-detail': () => import('./pages/CategoryPage').then((module) => ({ default: module.CategoryPage })),
  search: () => import('./pages/SearchPage').then((module) => ({ default: module.SearchPage })),
  'search-results': () => import('./pages/SearchResultsPage').then((module) => ({ default: module.SearchResultsPage })),
  'product-detail': () => import('./pages/ProductDetailPage').then((module) => ({ default: module.ProductDetailPage })),
  cart: () => import('./pages/CartPage').then((module) => ({ default: module.CartPage })),
  checkout: () => import('./pages/CheckoutPage').then((module) => ({ default: module.CheckoutPage })),
  'order-success': () => import('./pages/OrderSuccessPage').then((module) => ({ default: module.OrderSuccessPage })),
  payment: () => import('./pages/PaymentPage').then((module) => ({ default: module.PaymentPage })),
  profile: () => import('./pages/ProfilePage').then((module) => ({ default: module.ProfilePage })),
  'personal-data': () => import('./pages/PersonalDataPage').then((module) => ({ default: module.PersonalDataPage })),
  faq: () => import('./pages/FaqPage').then((module) => ({ default: module.FaqPage })),
  'not-found': () => import('./pages/NotFoundPage').then((module) => ({ default: module.NotFoundPage })),
} as const;

type LazyRouteId = keyof typeof routeLoaders;

const lazyRouteComponents = Object.fromEntries(
  Object.entries(routeLoaders).map(([routeId, loader]) => [routeId, React.lazy(loader)]),
) as unknown as Record<LazyRouteId, React.LazyExoticComponent<React.ComponentType>>;

registerRoutePrefetchers(routeLoaders);

function getLazyRouteId(pathname: string): LazyRouteId {
  if (pathname === '/') {
    return 'launch';
  }

  const routeId = getRouteId(pathname);
  return routeId in lazyRouteComponents ? routeId as LazyRouteId : 'not-found';
}

function getFallbackTitle(routeId: LazyRouteId) {
  if (routeId === 'main' || routeId === 'launch') {
    return 'MENS STYLE';
  }
  if (routeId === 'categories' || routeId === 'category-detail') {
    return 'Категории';
  }
  if (routeId === 'search' || routeId === 'search-results') {
    return 'Поиск';
  }
  if (routeId === 'cart') {
    return 'Покупки';
  }
  if (routeId === 'checkout') {
    return 'Оформление';
  }
  if (routeId === 'payment') {
    return 'Оплата';
  }
  if (routeId === 'profile' || routeId === 'personal-data') {
    return 'Профиль';
  }
  if (routeId === 'faq') {
    return 'FAQ';
  }
  return 'Страница';
}

function RouteFallback({ routeId }: { routeId: LazyRouteId }) {
  if (routeId === 'launch') {
    return (
      <div className="launch-screen route-fallback route-fallback--launch" role="status" aria-live="polite">
        <TopBar title="MENS STYLE" variant="feed" hideBack />
        <div className="route-fallback__block">
          <span className="skeleton route-fallback__logo" />
          <span className="skeleton route-fallback__line route-fallback__line--wide" />
          <span className="skeleton route-fallback__line" />
        </div>
      </div>
    );
  }

  return (
    <div className="page route-fallback" role="status" aria-live="polite">
      <TopBar
        title={getFallbackTitle(routeId)}
        variant={routeId === 'main' ? 'feed' : 'marketplace'}
        hideBack={routeId === 'main'}
      />
      <div className="route-fallback__grid" aria-hidden="true">
        {Array.from({ length: 4 }).map((_, index) => (
          <div className="route-fallback__card" key={index}>
            <span className="skeleton route-fallback__image" />
            <span className="skeleton route-fallback__line route-fallback__line--wide" />
            <span className="skeleton route-fallback__line" />
          </div>
        ))}
      </div>
    </div>
  );
}

function RouteSwitch() {
  const { currentPath, pathname } = useRouter();
  const routeId = getLazyRouteId(pathname);
  const Page = lazyRouteComponents[routeId];

  React.useEffect(() => {
    trackTelemetry('route.rendered', {
      route: normalizeRoute(pathname),
      ...getConnectionTelemetry(),
      ...getViewportTelemetry(),
    });
  }, [pathname]);

  const route = (
    <ChunkLoadRecovery resetKey={currentPath}>
      <React.Suspense fallback={<RouteFallback routeId={routeId} />}>
        <Page />
      </React.Suspense>
    </ChunkLoadRecovery>
  );

  if (routeId === 'launch') {
    return route;
  }

  return <AppShell>{route}</AppShell>;
}

export function App() {
  return (
    <AppErrorBoundary>
      <ThemeProvider>
        <RouterProvider>
          <NetworkProvider>
            <AuthProvider>
              <RouteSwitch />
            </AuthProvider>
          </NetworkProvider>
        </RouterProvider>
      </ThemeProvider>
    </AppErrorBoundary>
  );
}
