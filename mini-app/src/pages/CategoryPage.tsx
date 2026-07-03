import React from 'react';
import {
  ApiClientError,
  getCategory,
  getFavorites,
  getProducts,
  resolveCategory,
  toApiErrorMessage,
  type Category,
  type Product,
} from '../shared/api';
import { useAuth } from '../shared/auth/AuthProvider';
import { getNumericRouteParam, useRouter } from '../shared/router/RouterProvider';
import { EmptyState, ErrorState, InlineNotice, ProductCard, ProductGridSkeleton, TopBar } from '../shared/ui';
import { useProductActions } from '../features/catalog/useProductActions';

type CategoryPageRoute =
  | { mode: 'id'; categoryId: number; fallbackSlug: string }
  | { mode: 'slug'; categorySlug: string };

export function getCategoryPageRoute(pathname: string): CategoryPageRoute | null {
  const raw = pathname.replace('/category/', '').split('/')[0];
  if (!raw) {
    return null;
  }

  const categoryId = getNumericRouteParam(pathname, '/category/');
  if (categoryId && categoryId > 0 && /^\d+$/.test(raw)) {
    return { mode: 'id', categoryId, fallbackSlug: decodeURIComponent(raw) };
  }

  return { mode: 'slug', categorySlug: decodeURIComponent(raw) };
}

async function getCategoryBySlug(categorySlug: string) {
  return resolveCategory(categorySlug);
}

function withCurrentSearch(pathname: string, currentPath: string) {
  const url = new URL(currentPath, window.location.origin);
  return `${pathname}${url.search}`;
}

export function CategoryPage() {
  const { currentPath, pathname, navigate } = useRouter();
  const { isAuthenticated } = useAuth();
  const categoryRoute = React.useMemo(() => getCategoryPageRoute(pathname), [pathname]);
  const [category, setCategory] = React.useState<Category | null>(null);
  const [products, setProducts] = React.useState<Product[]>([]);
  const [favoriteIds, setFavoriteIds] = React.useState<Set<number>>(new Set());
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);
  const { addToCart, sizePicker, toggleFavorite, notice, clearNotice } = useProductActions({
    favoriteIds,
    setFavoriteIds,
  });

  React.useEffect(() => {
    let cancelled = false;

    async function load() {
      if (!categoryRoute) {
        setError('Категория не найдена');
        setLoading(false);
        return;
      }

      setLoading(true);
      setError(null);
      try {
        let categoryResult: Category | null = null;
        if (categoryRoute.mode === 'id') {
          try {
            categoryResult = await getCategory(categoryRoute.categoryId);
          } catch (categoryError) {
            if (!(categoryError instanceof ApiClientError) || categoryError.status !== 404) {
              throw categoryError;
            }
            categoryResult = await getCategoryBySlug(categoryRoute.fallbackSlug);
          }
        } else {
          categoryResult = await getCategoryBySlug(categoryRoute.categorySlug);
        }
        if (!categoryResult) {
          throw new Error('Категория не найдена');
        }
        if (categoryRoute.mode === 'slug' && categoryResult.slug !== categoryRoute.categorySlug) {
          const canonicalPath = withCurrentSearch(
            `/category/${encodeURIComponent(categoryResult.slug)}`,
            currentPath,
          );
          if (canonicalPath !== currentPath) {
            navigate(canonicalPath, { replace: true });
          }
        }
        const [productResult, favoriteResult] = await Promise.all([
          getProducts({ limit: 100, offset: 0, status: 'ACTIVE', category_id: categoryResult.id }),
          isAuthenticated ? getFavorites().catch(() => ({ items: [] })) : Promise.resolve({ items: [] }),
        ]);

        if (!cancelled) {
          setCategory(categoryResult);
          setProducts(productResult.items);
          setFavoriteIds(new Set(favoriteResult.items.map((favorite) => favorite.product_id)));
        }
      } catch (loadError) {
        if (!cancelled) {
          setError(toApiErrorMessage(loadError));
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    void load();
    return () => {
      cancelled = true;
    };
  }, [categoryRoute, currentPath, isAuthenticated, navigate]);

  return (
    <div className="page">
      <TopBar title={category?.name ?? 'Категория'} variant="marketplace" backFallback="/categories" />

      {notice ? (
        <InlineNotice tone={notice.includes('добавлен') ? 'success' : 'warning'}>
          <span>{notice}</span>
          <button type="button" onClick={clearNotice}>
            ×
          </button>
        </InlineNotice>
      ) : null}

      {loading ? <ProductGridSkeleton count={6} /> : null}
      {!loading && error ? <ErrorState message={error} actionLabel="К категориям" onAction={() => navigate('/categories')} /> : null}
      {!loading && !error && products.length === 0 ? (
        <EmptyState title="Товаров пока нет" message="В этой категории товары появятся позже." />
      ) : null}
      {!loading && !error && products.length > 0 ? (
        <div className="product-grid">
          {products.map((product) => (
            <ProductCard
              favorite={favoriteIds.has(product.id)}
              key={product.id}
              product={product}
              onAddToCart={addToCart}
              onFavoriteToggle={toggleFavorite}
            />
          ))}
        </div>
      ) : null}
      {sizePicker}
    </div>
  );
}
