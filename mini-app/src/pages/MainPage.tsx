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
  const [feedQuery, setFeedQuery] = React.useState('');
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

  const horizontalBanners = banners.filter((banner) => !banner.display_type || banner.display_type === 'horizontal');
  const verticalBanners = banners.filter((banner) => banner.display_type === 'vertical');

  function submitFeedSearch(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const query = feedQuery.trim();
    navigate(query ? `/search/results?q=${encodeURIComponent(query)}` : '/search/results');
  }

  return (
    <div className="page page--feed">
      <TopBar
        title="Gadji Store"
        variant="marketplace"
        right={
          <button className="avatar-button" type="button" onClick={() => navigate('/profile')} aria-label="Профиль">
            {telegramUser?.photo_url ? <img src={telegramUser.photo_url} alt="" /> : '◌'}
          </button>
        }
      />
      <form className="search-row search-row--feed" onSubmit={submitFeedSearch}>
        <label className="search-field search-field--input">
          <span>⌕</span>
          <input
            value={feedQuery}
            onChange={(event) => setFeedQuery(event.target.value)}
            placeholder="Найти одежду, бренд, размер..."
            type="search"
          />
        </label>
        <button className="search-submit-button" type="submit" aria-label="Искать">
          Найти
        </button>
      </form>

      {notice ? (
        <InlineNotice tone={notice.includes('добавлен') ? 'success' : 'warning'}>
          <span>{notice}</span>
          <button type="button" onClick={clearNotice}>
            ×
          </button>
        </InlineNotice>
      ) : null}

      {horizontalBanners.length > 0 ? <BannerCarousel banners={horizontalBanners} /> : null}
      {verticalBanners.length > 0 ? <VerticalBannerGrid banners={verticalBanners} /> : null}

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
      navigate(`/category/${banner.target_id}`);
      return;
    }

    if (banner.external_url) {
      window.location.href = banner.external_url;
    }
  }

  return (
    <button className={`native-banner ${imageUrl ? 'native-banner--with-image' : ''}`} type="button" onClick={openBanner}>
      {imageUrl ? (
        <span className="native-banner__image" aria-hidden="true">
          <img src={imageUrl} alt="" />
        </span>
      ) : null}
      <span className="native-banner__content">
        <strong>{banner.title}</strong>
        {banner.subtitle ? <small>{banner.subtitle}</small> : null}
        <em>Смотреть</em>
      </span>
    </button>
  );
}

function VerticalBannerGrid({ banners }: { banners: Banner[] }) {
  return (
    <section className="vertical-banner-grid" aria-label="Вертикальные акции">
      {banners.map((banner) => (
        <VerticalBannerCard banner={banner} key={banner.id} />
      ))}
    </section>
  );
}

function VerticalBannerCard({ banner }: { banner: Banner }) {
  const { navigate } = useRouter();
  const imageUrl = normalizeAssetUrl(banner.image_url || banner.image_path);

  function openBanner() {
    if (banner.target_type === 'product' && banner.target_id) {
      navigate(`/product/${banner.target_id}`);
      return;
    }

    if (banner.target_type === 'category' && banner.target_id) {
      navigate(`/category/${banner.target_id}`);
      return;
    }

    if (banner.external_url) {
      window.open(banner.external_url, '_blank', 'noopener,noreferrer');
    }
  }

  return (
    <button className="vertical-banner-card" type="button" onClick={openBanner}>
      <span className="vertical-banner-card__media" aria-hidden="true">
        {imageUrl ? <img src={imageUrl} alt="" /> : <span>{banner.title.slice(0, 1).toUpperCase()}</span>}
      </span>
      <span className="vertical-banner-card__body">
        <strong>{banner.title}</strong>
        {banner.subtitle ? <small>{banner.subtitle}</small> : null}
      </span>
    </button>
  );
}

function BannerCarousel({ banners }: { banners: Banner[] }) {
  const trackRef = React.useRef<HTMLDivElement | null>(null);
  const interactionPauseUntil = React.useRef(0);
  const [activeIndex, setActiveIndex] = React.useState(0);
  const hasMultipleBanners = banners.length > 1;

  const updateActiveIndex = React.useCallback(() => {
    const track = trackRef.current;
    if (!track) {
      return;
    }

    const nextIndex = Math.round(track.scrollLeft / Math.max(track.clientWidth, 1));
    setActiveIndex(Math.min(Math.max(nextIndex, 0), banners.length - 1));
  }, [banners.length]);

  React.useEffect(() => {
    if (!hasMultipleBanners) {
      return undefined;
    }

    const timer = window.setInterval(() => {
      const track = trackRef.current;
      if (!track || Date.now() < interactionPauseUntil.current) {
        return;
      }

      const nextIndex = (activeIndex + 1) % banners.length;
      track.scrollTo({ left: track.clientWidth * nextIndex, behavior: 'smooth' });
      setActiveIndex(nextIndex);
    }, 4500);

    return () => window.clearInterval(timer);
  }, [activeIndex, banners.length, hasMultipleBanners]);

  function pauseAutoplay() {
    interactionPauseUntil.current = Date.now() + 7000;
  }

  function scrollToBanner(index: number) {
    const track = trackRef.current;
    pauseAutoplay();
    track?.scrollTo({ left: track.clientWidth * index, behavior: 'smooth' });
    setActiveIndex(index);
  }

  return (
    <section className="banner-carousel" aria-label="Акции">
      <div
        className="banner-carousel__track"
        ref={trackRef}
        onPointerDown={pauseAutoplay}
        onScroll={updateActiveIndex}
      >
        {banners.map((banner) => (
          <div className="banner-carousel__slide" key={banner.id}>
            <MainBanner banner={banner} />
          </div>
        ))}
      </div>
      {hasMultipleBanners ? (
        <div className="banner-dots" aria-label="Баннеры">
          {banners.map((banner, index) => (
            <button
              className={activeIndex === index ? 'is-active' : ''}
              key={banner.id}
              type="button"
              aria-label={`Баннер ${index + 1}`}
              onClick={() => scrollToBanner(index)}
            />
          ))}
        </div>
      ) : null}
    </section>
  );
}
