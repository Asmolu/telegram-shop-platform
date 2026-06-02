import React from 'react';
import { getFavorites, getProducts, toApiErrorMessage, type Product } from '../shared/api';
import { useAuth } from '../shared/auth/AuthProvider';
import { useRouter } from '../shared/router/RouterProvider';
import { EmptyState, ErrorState, InlineNotice, ProductCard, ProductGridSkeleton, TopBar } from '../shared/ui';
import { useProductActions } from '../features/catalog/useProductActions';

export function SearchResultsPage() {
  const { searchParams, navigate } = useRouter();
  const { isAuthenticated } = useAuth();
  const [products, setProducts] = React.useState<Product[]>([]);
  const [favoriteIds, setFavoriteIds] = React.useState<Set<number>>(new Set());
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);
  const { addToCart, toggleFavorite, notice, clearNotice } = useProductActions({
    favoriteIds,
    setFavoriteIds,
  });

  const query = searchParams.get('q') ?? '';
  const categoryId = searchParams.get('category_id');
  const tagId = searchParams.get('tag_id');
  const size = searchParams.get('size') ?? '';
  const color = searchParams.get('color') ?? '';
  const sort = searchParams.get('sort') ?? 'newest';
  const priceFrom = Number(searchParams.get('price_from') ?? 0);
  const priceTo = Number(searchParams.get('price_to') ?? 0);
  const categoryName = searchParams.get('category');

  React.useEffect(() => {
    let cancelled = false;

    async function load() {
      setLoading(true);
      setError(null);
      try {
        const [productResult, favoriteResult] = await Promise.all([
          getProducts({
            limit: 100,
            offset: 0,
            status: 'ACTIVE',
            search: query || undefined,
            category_id: categoryId ? Number(categoryId) : undefined,
            tag_id: tagId ? Number(tagId) : undefined,
          }),
          isAuthenticated ? getFavorites().catch(() => ({ items: [] })) : Promise.resolve({ items: [] }),
        ]);

        if (!cancelled) {
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
  }, [categoryId, isAuthenticated, query, tagId]);

  const filtered = products
    .filter((product) => {
      const price = Number(product.base_price);
      const matchesPriceFrom = priceFrom ? price >= priceFrom : true;
      const matchesPriceTo = priceTo ? price <= priceTo : true;
      const matchesSize = size
        ? product.variants.some((variant) => variant.size.toLowerCase() === size.toLowerCase())
        : true;
      const matchesColor = color
        ? product.variants.some((variant) => variant.color?.toLowerCase().includes(color.toLowerCase()))
        : true;
      return matchesPriceFrom && matchesPriceTo && matchesSize && matchesColor;
    })
    .sort((left, right) => {
      if (sort === 'price_asc') {
        return Number(left.base_price) - Number(right.base_price);
      }
      if (sort === 'price_desc') {
        return Number(right.base_price) - Number(left.base_price);
      }
      return new Date(right.created_at).getTime() - new Date(left.created_at).getTime();
    });

  function changeSort(nextSort: string) {
    const params = new URLSearchParams(searchParams);
    params.set('sort', nextSort);
    navigate(`/search/results?${params.toString()}`);
  }

  return (
    <div className="page">
      <TopBar title={categoryName || 'Результаты'} onBack={() => navigate('/search')} />
      <button className="search-field search-field--static" type="button" onClick={() => navigate('/search')}>
        <span>⌕</span>
        {query || 'Найти одежду, бренд, размер...'}
      </button>
      <div className="sort-row">
        {[
          ['newest', 'Сначала новые'],
          ['price_asc', 'Дешевле'],
          ['price_desc', 'Дороже'],
        ].map(([value, label]) => (
          <button className={sort === value ? 'is-selected' : ''} key={value} type="button" onClick={() => changeSort(value)}>
            {label}
          </button>
        ))}
      </div>

      {notice ? (
        <InlineNotice tone={notice.includes('добавлен') ? 'success' : 'warning'}>
          <span>{notice}</span>
          <button type="button" onClick={clearNotice}>
            ×
          </button>
        </InlineNotice>
      ) : null}

      {loading ? <ProductGridSkeleton count={6} /> : null}
      {!loading && error ? <ErrorState message={error} /> : null}
      {!loading && !error && filtered.length === 0 ? (
        <EmptyState
          title="Ничего не найдено"
          message="Попробуйте изменить запрос или фильтры."
          actionLabel="Сбросить фильтры"
          onAction={() => navigate('/search/results')}
        />
      ) : null}
      {!loading && !error && filtered.length > 0 ? (
        <div className="product-grid">
          {filtered.map((product) => (
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
    </div>
  );
}
