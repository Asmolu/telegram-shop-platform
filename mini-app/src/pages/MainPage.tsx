import React from 'react';
import {
  getBanners,
  getFavorites,
  getProducts,
  toApiErrorMessage,
  type Banner,
  type Product,
} from '../shared/api';
import { useAuth } from '../shared/auth/AuthProvider';
import { useRouter } from '../shared/router/RouterProvider';
import { EmptyState, ErrorState, InlineNotice, ProductCard, ProductGridSkeleton, TopBar } from '../shared/ui';
import { normalizeAssetUrl } from '../shared/utils/images';
import { useProductActions } from '../features/catalog/useProductActions';

export function MainPage() {
  const { navigate } = useRouter();
  const { isAuthenticated, telegramUser } = useAuth();
  const [products, setProducts] = React.useState<Product[]>([]);
  const [banners, setBanners] = React.useState<Banner[]>([]);
  const [favoriteIds, setFavoriteIds] = React.useState<Set<number>>(new Set());
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);
  const { addToCart, toggleFavorite, notice, clearNotice } = useProductActions({
    favoriteIds,
    setFavoriteIds,
  });

  React.useEffect(() => {
    let cancelled = false;

    async function load() {
      setLoading(true);
      setError(null);
      try {
        const [productResult, bannerResult, favoriteResult] = await Promise.all([
          getProducts({ limit: 40, offset: 0, status: 'ACTIVE' }),
          getBanners().catch(() => ({ items: [], meta: { limit: 20, offset: 0, total: 0 } })),
          isAuthenticated ? getFavorites().catch(() => ({ items: [] })) : Promise.resolve({ items: [] }),
        ]);

        if (!cancelled) {
          setProducts(productResult.items);
          setBanners(bannerResult.items);
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
  }, [isAuthenticated]);

  const activeBanner = banners[0];

  return (
    <div className="page page--feed">
      <TopBar
        title="Gadji Store"
        right={
          <button className="avatar-button" type="button" onClick={() => navigate('/profile')} aria-label="Профиль">
            {telegramUser?.photo_url ? <img src={telegramUser.photo_url} alt="" /> : '◌'}
          </button>
        }
      />
      <div className="search-row">
        <button className="faq-button" type="button" onClick={() => navigate('/faq')} aria-label="FAQ">
          ?
        </button>
        <button className="search-field" type="button" onClick={() => navigate('/search')}>
          <span>⌕</span>
          Найти одежду, бренд, размер...
        </button>
      </div>

      {notice ? (
        <InlineNotice tone={notice.includes('добавлен') ? 'success' : 'warning'}>
          <span>{notice}</span>
          <button type="button" onClick={clearNotice}>
            ×
          </button>
        </InlineNotice>
      ) : null}

      {activeBanner ? <MainBanner banner={activeBanner} /> : null}

      <div className="feed-chips" aria-label="Быстрые фильтры">
        <button type="button" onClick={() => navigate('/search/results?tag=new')}>
          Новинки
        </button>
        <button type="button" onClick={() => navigate('/search/results?tag=sale')}>
          Скидки
        </button>
        <button type="button" onClick={() => navigate('/search/results?tag=premium')}>
          Premium
        </button>
      </div>

      {loading ? <ProductGridSkeleton count={6} /> : null}
      {!loading && error ? <ErrorState message={error} actionLabel="Повторить" onAction={() => window.location.reload()} /> : null}
      {!loading && !error && products.length === 0 ? (
        <EmptyState title="Товары скоро появятся" message="Каталог пока пуст." />
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
    </div>
  );
}

function MainBanner({ banner }: { banner: Banner }) {
  const { navigate } = useRouter();
  const imageUrl = normalizeAssetUrl(banner.image_url || banner.image_path);

  function openBanner() {
    if (banner.target_type === 'product' && banner.target_id) {
      navigate(`/product/${banner.target_id}`);
      return;
    }

    if (banner.target_type === 'category' && banner.target_id) {
      navigate(`/search/results?category_id=${banner.target_id}`);
      return;
    }

    if (banner.external_url) {
      window.location.href = banner.external_url;
    }
  }

  return (
    <button className="native-banner" type="button" onClick={openBanner}>
      <span>
        <strong>{banner.title}</strong>
        {banner.subtitle ? <small>{banner.subtitle}</small> : null}
        <em>Смотреть</em>
      </span>
      {imageUrl ? <img src={imageUrl} alt="" /> : null}
    </button>
  );
}
