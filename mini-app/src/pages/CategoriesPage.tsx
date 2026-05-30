import React from 'react';
import { getCategories, getProducts, toApiErrorMessage, type Category, type Product } from '../shared/api';
import { useRouter } from '../shared/router/RouterProvider';
import { EmptyState, ErrorState, PageLoader, TopBar } from '../shared/ui';
import { pluralizeProducts } from '../shared/utils/format';
import { getProductImageUrl } from '../shared/utils/images';

export function CategoriesPage() {
  const { navigate } = useRouter();
  const [categories, setCategories] = React.useState<Category[]>([]);
  const [products, setProducts] = React.useState<Product[]>([]);
  const [query, setQuery] = React.useState('');
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);

  React.useEffect(() => {
    let cancelled = false;
    async function load() {
      setLoading(true);
      setError(null);
      try {
        const [categoryResult, productResult] = await Promise.all([
          getCategories(),
          getProducts({ limit: 100, offset: 0, status: 'ACTIVE' }),
        ]);
        if (!cancelled) {
          setCategories(categoryResult);
          setProducts(productResult.items);
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
  }, []);

  const filtered = categories.filter((category) => category.name.toLowerCase().includes(query.toLowerCase()));

  return (
    <div className="page">
      <TopBar title="Категории" />
      <label className="input-shell">
        <span>⌕</span>
        <input
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Найти категорию"
          type="search"
        />
      </label>

      {loading ? <PageLoader text="Загружаем категории..." /> : null}
      {!loading && error ? <ErrorState message={error} actionLabel="Повторить" onAction={() => window.location.reload()} /> : null}
      {!loading && !error && filtered.length === 0 ? <EmptyState title="Категории не найдены" /> : null}

      {!loading && !error && filtered.length > 0 ? (
        <div className="category-grid">
          {filtered.map((category) => {
            const categoryProducts = products.filter((product) => product.category_id === category.id);
            const imageUrl = categoryProducts[0] ? getProductImageUrl(categoryProducts[0]) : null;

            return (
              <button
                className="category-card"
                key={category.id}
                type="button"
                onClick={() => navigate(`/search/results?category_id=${category.id}&category=${encodeURIComponent(category.name)}`)}
              >
                <span className="category-card__media">
                  {imageUrl ? <img src={imageUrl} alt="" /> : <span>{category.name.slice(0, 1).toUpperCase()}</span>}
                </span>
                <strong>{category.name}</strong>
                <small>{pluralizeProducts(categoryProducts.length)}</small>
                {categoryProducts.some((product) => product.tags.some((tag) => tag.slug.includes('sale'))) ? (
                  <em>sale</em>
                ) : null}
              </button>
            );
          })}
        </div>
      ) : null}
    </div>
  );
}
