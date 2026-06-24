import React from 'react';
import {
  getCategories,
  getProducts,
  getTags,
  toApiErrorMessage,
  type Category,
  type Product,
  type Tag,
} from '../shared/api';
import { useRouter } from '../shared/router/RouterProvider';
import { EmptyState, ErrorState, PageLoader, TopBar } from '../shared/ui';
import { getProductImageUrl, normalizeAssetUrl } from '../shared/utils/images';

export function CategoriesPage() {
  const { navigate } = useRouter();
  const [categories, setCategories] = React.useState<Category[]>([]);
  const [tags, setTags] = React.useState<Tag[]>([]);
  const [products, setProducts] = React.useState<Product[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);

  React.useEffect(() => {
    let cancelled = false;
    async function load() {
      setLoading(true);
      setError(null);
      try {
        const [categoryResult, tagResult, productResult] = await Promise.all([
          getCategories(),
          getTags(),
          getProducts({ limit: 100, offset: 0, status: 'ACTIVE' }),
        ]);
        if (!cancelled) {
          setCategories(categoryResult);
          setTags(tagResult);
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

  return (
    <div className="page page--gradient-header">
      <TopBar title="Категории" variant="marketplace" />

      {loading ? <PageLoader text="Загружаем категории..." /> : null}
      {!loading && error ? <ErrorState message={error} actionLabel="Повторить" onAction={() => window.location.reload()} /> : null}
      {!loading && !error && categories.length === 0 && tags.length === 0 ? (
        <EmptyState title="Категории и подборки не найдены" />
      ) : null}

      {!loading && !error && categories.length > 0 ? (
        <div className="category-grid">
          {categories.map((category) => {
            const categoryProducts = products.filter((product) => isProductInCategory(product, category.id));
            const categoryImageUrl = normalizeAssetUrl(
              category.image_url
                ?? (category.image_path ? `/uploads/${category.image_path}` : null),
            );
            const imageUrl = categoryImageUrl
              ?? (categoryProducts[0] ? getProductImageUrl(categoryProducts[0], 'card') : null);

            return (
              <button
                className="category-card"
                key={category.id}
                type="button"
                onClick={() => navigate(`/category/${category.id}`)}
              >
                <span className="category-card__media">
                  {imageUrl ? (
                    <img
                      src={imageUrl}
                      alt=""
                      width={480}
                      height={360}
                      loading="lazy"
                      decoding="async"
                    />
                  ) : <span>{category.name.slice(0, 1).toUpperCase()}</span>}
                </span>
                <strong>{category.name}</strong>
                {categoryProducts.some((product) => product.tags.some((tag) => tag.slug.includes('sale'))) ? (
                  <em>sale</em>
                ) : null}
              </button>
            );
          })}
        </div>
      ) : null}

      {!loading && !error && tags.length > 0 ? (
        <section className="taxonomy-section">
          <div className="taxonomy-section__heading">
            <h2>Подборки</h2>
            <p>Товары по тегам</p>
          </div>
          <div className="category-grid">
            {tags.map((tag) => {
              const imageUrl = normalizeAssetUrl(
                tag.image_url ?? (tag.image_path ? `/uploads/${tag.image_path}` : null),
              );

              return (
                <button
                  className="category-card category-card--tag"
                  key={tag.id}
                  type="button"
                  onClick={() =>
                    navigate(
                      `/search/results?tag_id=${tag.id}&tag=${encodeURIComponent(tag.name)}&from=categories`,
                    )
                  }
                >
                  <span className="category-card__media">
                    {imageUrl ? (
                      <img
                        src={imageUrl}
                        alt=""
                        width={480}
                        height={360}
                        loading="lazy"
                        decoding="async"
                      />
                    ) : <span>{tag.name.slice(0, 1).toUpperCase()}</span>}
                  </span>
                  <strong>{tag.name}</strong>
                </button>
              );
            })}
          </div>
        </section>
      ) : null}
    </div>
  );
}

function isProductInCategory(product: Product, categoryId: number) {
  if (product.category_id === categoryId) {
    return true;
  }

  return Boolean(product.categories?.some((assignment) => assignment.category_id === categoryId));
}
