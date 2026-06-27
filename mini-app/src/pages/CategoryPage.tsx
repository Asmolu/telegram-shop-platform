import React from 'react';
import {
  getCategory,
  getFavorites,
  getProducts,
  toApiErrorMessage,
  type Category,
  type Product,
} from '../shared/api';
import { useAuth } from '../shared/auth/AuthProvider';
import { getNumericRouteParam, useRouter } from '../shared/router/RouterProvider';
import { EmptyState, ErrorState, InlineNotice, ProductCard, ProductGridSkeleton, TopBar } from '../shared/ui';
import { useProductActions } from '../features/catalog/useProductActions';

export function CategoryPage() {
  const { pathname, navigate } = useRouter();
  const { isAuthenticated } = useAuth();
  const categoryId = getNumericRouteParam(pathname, '/category/');
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
      if (!categoryId) {
        setError('Категория не найдена');
        setLoading(false);
        return;
      }

      setLoading(true);
      setError(null);
      try {
        const [categoryResult, productResult, favoriteResult] = await Promise.all([
          getCategory(categoryId),
          getProducts({ limit: 100, offset: 0, status: 'ACTIVE', category_id: categoryId }),
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
  }, [categoryId, isAuthenticated]);

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
