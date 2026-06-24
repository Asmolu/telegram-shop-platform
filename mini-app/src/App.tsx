import { AuthProvider } from './shared/auth/AuthProvider';
import { NetworkProvider } from './shared/network/NetworkProvider';
import { RouterProvider, getRouteId, useRouter } from './shared/router/RouterProvider';
import { ThemeProvider } from './shared/theme/ThemeProvider';
import { AppShell, TopBar } from './shared/ui';
import { CartPage } from './pages/CartPage';
import { CategoryPage } from './pages/CategoryPage';
import { CategoriesPage } from './pages/CategoriesPage';
import { CheckoutPage } from './pages/CheckoutPage';
import { FaqPage } from './pages/FaqPage';
import { LaunchPage } from './pages/LaunchPage';
import { MainPage } from './pages/MainPage';
import { OrderSuccessPage } from './pages/OrderSuccessPage';
import { PaymentPage } from './pages/PaymentPage';
import { PersonalDataPage } from './pages/PersonalDataPage';
import { ProductDetailPage } from './pages/ProductDetailPage';
import { ProfilePage } from './pages/ProfilePage';
import { SearchPage } from './pages/SearchPage';
import { SearchResultsPage } from './pages/SearchResultsPage';
import type React from 'react';

function RouteSwitch() {
  const { pathname, navigate } = useRouter();
  const routeId = getRouteId(pathname);

  if (pathname === '/') {
    return <LaunchPage />;
  }

  let page: React.ReactElement;

  switch (routeId) {
    case 'main':
      page = <MainPage />;
      break;
    case 'categories':
      page = <CategoriesPage />;
      break;
    case 'category-detail':
      page = <CategoryPage />;
      break;
    case 'search':
      page = <SearchPage />;
      break;
    case 'search-results':
      page = <SearchResultsPage />;
      break;
    case 'product-detail':
      page = <ProductDetailPage />;
      break;
    case 'cart':
      page = <CartPage />;
      break;
    case 'checkout':
      page = <CheckoutPage />;
      break;
    case 'order-success':
      page = <OrderSuccessPage />;
      break;
    case 'payment':
      page = <PaymentPage />;
      break;
    case 'profile':
      page = <ProfilePage />;
      break;
    case 'personal-data':
      page = <PersonalDataPage />;
      break;
    case 'faq':
      page = <FaqPage />;
      break;
    default:
      page = (
        <div className="page">
          <TopBar title="Страница не найдена" backFallback="/main" />
          <section className="state-block">
            <h1>Страница не найдена</h1>
            <button className="primary-button" type="button" onClick={() => navigate('/main')}>
              К товарам
            </button>
          </section>
        </div>
      );
  }

  return <AppShell>{page}</AppShell>;
}

export function App() {
  return (
    <ThemeProvider>
      <RouterProvider>
        <NetworkProvider>
          <AuthProvider>
            <RouteSwitch />
          </AuthProvider>
        </NetworkProvider>
      </RouterProvider>
    </ThemeProvider>
  );
}
