import React from 'react';

type NavigateOptions = {
  replace?: boolean;
};

type RouterContextValue = {
  currentPath: string;
  pathname: string;
  searchParams: URLSearchParams;
  navigate: (to: string, options?: NavigateOptions) => void;
};

const RouterContext = React.createContext<RouterContextValue | null>(null);

function getCurrentPath() {
  return `${window.location.pathname}${window.location.search}`;
}

export function RouterProvider({ children }: { children: React.ReactNode }) {
  const [location, setLocation] = React.useState(getCurrentPath);

  React.useEffect(() => {
    const onPopState = () => setLocation(getCurrentPath());
    window.addEventListener('popstate', onPopState);
    return () => window.removeEventListener('popstate', onPopState);
  }, []);

  const navigate = React.useCallback((to: string, options: NavigateOptions = {}) => {
    if (to === getCurrentPath()) {
      return;
    }

    if (options.replace) {
      window.history.replaceState({}, '', to);
    } else {
      window.history.pushState({}, '', to);
    }

    setLocation(getCurrentPath());
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }, []);

  const value = React.useMemo(() => {
    const url = new URL(location, window.location.origin);
    return {
      currentPath: `${url.pathname}${url.search}`,
      pathname: url.pathname,
      searchParams: url.searchParams,
      navigate,
    };
  }, [location, navigate]);

  return <RouterContext.Provider value={value}>{children}</RouterContext.Provider>;
}

export function useRouter() {
  const context = React.useContext(RouterContext);
  if (!context) {
    throw new Error('useRouter must be used within RouterProvider');
  }

  return context;
}

export function Link({
  to,
  className,
  children,
  title,
}: {
  to: string;
  className?: string;
  children: React.ReactNode;
  title?: string;
}) {
  const { navigate } = useRouter();

  return (
    <a
      className={className}
      href={to}
      title={title}
      onClick={(event) => {
        event.preventDefault();
        navigate(to);
      }}
    >
      {children}
    </a>
  );
}

export function getRouteId(pathname: string) {
  if (pathname === '/' || pathname === '/main') {
    return 'main';
  }
  if (pathname === '/categories') {
    return 'categories';
  }
  if (pathname.startsWith('/category/')) {
    return 'category-detail';
  }
  if (pathname === '/search') {
    return 'search';
  }
  if (pathname === '/search/results') {
    return 'search-results';
  }
  if (pathname.startsWith('/product/')) {
    return 'product-detail';
  }
  if (pathname === '/cart') {
    return 'cart';
  }
  if (pathname === '/checkout') {
    return 'checkout';
  }
  if (pathname.startsWith('/order-success/')) {
    return 'order-success';
  }
  if (pathname.startsWith('/payment/')) {
    return 'payment';
  }
  if (pathname === '/profile') {
    return 'profile';
  }
  if (pathname === '/profile/personal-data') {
    return 'personal-data';
  }
  if (pathname === '/faq') {
    return 'faq';
  }
  return 'not-found';
}

export function getNumericRouteParam(pathname: string, prefix: string) {
  const raw = pathname.replace(prefix, '').split('/')[0];
  const value = Number(raw);
  return Number.isFinite(value) ? value : null;
}

export function getSafeReturnTo(value: string | null | undefined, fallback = '/main') {
  if (!value || value.startsWith('//') || !value.startsWith('/') || value.includes('\\')) {
    return fallback;
  }

  try {
    const url = new URL(value, window.location.origin);
    if (url.origin !== window.location.origin || getRouteId(url.pathname) === 'not-found') {
      return fallback;
    }

    const path = `${url.pathname}${url.search}`;
    return path === '/' ? fallback : path;
  } catch {
    return fallback;
  }
}

export function withReturnTo(to: string, returnTo: string | null | undefined) {
  const safeReturnTo = getSafeReturnTo(returnTo, '');
  if (!safeReturnTo) {
    return to;
  }

  const url = new URL(to, window.location.origin);
  url.searchParams.set('returnTo', safeReturnTo);
  return `${url.pathname}${url.search}`;
}

export function getAuthPath(returnTo: string | null | undefined) {
  return withReturnTo('/', returnTo);
}
