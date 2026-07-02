import React from 'react';
import {
  getBanners,
  getFavorites,
  getLooks,
  getProducts,
  trackBannerClick,
  toApiErrorMessage,
  type Banner,
  type LookCard as LookCardType,
  type Product,
} from '../shared/api';
import { useAuth } from '../shared/auth/AuthProvider';
import { SearchAutocomplete } from '../features/catalog/SearchAutocomplete';
import { scheduleRoutePrefetch } from '../shared/router/routePrefetch';
import { Link, useRouter, withReturnTo } from '../shared/router/RouterProvider';
import { EmptyState, ErrorState, InlineNotice, LookCard, ProductCard, ProductGridSkeleton, TopBar } from '../shared/ui';
import { copyTextToClipboard, getBannerAction, getBannerCtaLabel } from '../shared/utils/banners';
import { normalizeAssetUrl } from '../shared/utils/images';
import { getMotionAwareScrollBehavior } from '../shared/utils/motion';
import { useProductActions } from '../features/catalog/useProductActions';

export function MainPage() {
  const { navigate } = useRouter();
  const { isAuthenticated } = useAuth();
  const [products, setProducts] = React.useState<Product[]>([]);
  const [looks, setLooks] = React.useState<LookCardType[]>([]);
  const [banners, setBanners] = React.useState<Banner[]>([]);
  const [favoriteIds, setFavoriteIds] = React.useState<Set<number>>(new Set());
  const [feedQuery, setFeedQuery] = React.useState('');
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);
  const [bannerNotice, setBannerNotice] = React.useState<string | null>(null);
  const { addToCart, sizePicker, toggleFavorite, notice, clearNotice } = useProductActions({
    favoriteIds,
    setFavoriteIds,
  });

  React.useEffect(() => {
    let cancelled = false;

    async function load() {
      setLoading(true);
      setError(null);
      try {
        const [productResult, lookResult, bannerResult, favoriteResult] = await Promise.all([
          getProducts({ limit: 40, offset: 0, status: 'ACTIVE' }),
          getLooks({ limit: 8, offset: 0 }).catch(() => ({ items: [], meta: { limit: 8, offset: 0, total: 0 } })),
          getBanners().catch(() => ({ items: [], meta: { limit: 20, offset: 0, total: 0 } })),
          isAuthenticated ? getFavorites().catch(() => ({ items: [] })) : Promise.resolve({ items: [] }),
        ]);

        if (!cancelled) {
          setProducts(productResult.items);
          setLooks(lookResult.items);
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

  React.useEffect(() => {
    if (loading || error || products.length === 0) {
      return undefined;
    }

    return scheduleRoutePrefetch('product-detail');
  }, [error, loading, products.length]);

  const horizontalBanners = banners.filter((banner) => banner.display_type === 'horizontal');
  const verticalBanners = banners.filter((banner) => banner.display_type === 'vertical');

  function navigateToFeedSearch(nextQuery = feedQuery) {
    const query = nextQuery.trim();
    navigate(query ? `/search/results?q=${encodeURIComponent(query)}` : '/search/results');
  }

  function submitFeedSearch(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    navigateToFeedSearch();
  }

  return (
    <div className="page page--feed">
      <TopBar
        title="ICON STORE"
        variant="feed"
      >
        <form onSubmit={submitFeedSearch}>
          <SearchAutocomplete
            className="search-row--feed"
            value={feedQuery}
            onChange={setFeedQuery}
            onSearch={navigateToFeedSearch}
            placeholder="Найти одежду, бренд, размер..."
            submitLabel="Найти"
            submitAriaLabel="Искать"
          />
        </form>
      </TopBar>

      {notice ? (
        <InlineNotice tone={notice.includes('добавлен') ? 'success' : 'warning'}>
          <span>{notice}</span>
          <button type="button" onClick={clearNotice}>
            ×
          </button>
        </InlineNotice>
      ) : null}

      {bannerNotice ? (
        <InlineNotice tone={bannerNotice.includes('скопирован') ? 'success' : 'warning'}>
          <span>{bannerNotice}</span>
          <button type="button" onClick={() => setBannerNotice(null)}>
            ×
          </button>
        </InlineNotice>
      ) : null}

      {horizontalBanners.length > 0 ? <BannerCarousel banners={horizontalBanners} onNotice={setBannerNotice} /> : null}
      {verticalBanners.length > 0 ? <VerticalBannerGrid banners={verticalBanners} onNotice={setBannerNotice} /> : null}
      {!loading && !error && looks.length > 0 ? <LooksSection looks={looks} /> : null}

      {loading ? <ProductGridSkeleton count={6} /> : null}
      {!loading && error ? <ErrorState message={error} actionLabel="Повторить" onAction={() => window.location.reload()} /> : null}
      {!loading && !error && products.length === 0 ? (
        <EmptyState title="Товары скоро появятся" message="Каталог пока пуст." />
      ) : null}
      {!loading && !error && products.length > 0 ? (
        <div className="product-grid">
          {products.map((product, index) => (
            <ProductCard
              favorite={favoriteIds.has(product.id)}
              imageFetchPriority={index === 0 ? 'high' : 'auto'}
              imageLoading={index === 0 ? 'eager' : 'lazy'}
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

function LooksSection({ looks }: { looks: LookCardType[] }) {
  return (
    <section className="looks-section" aria-labelledby="looks-section-title">
      <div className="section-heading looks-section__heading">
        <div>
          <span>Готовые комплекты</span>
          <h2 id="looks-section-title">Образы</h2>
        </div>
        <Link className="section-link" to="/looks">Все</Link>
      </div>
      <div className="looks-carousel__track" data-swipe-back-ignore>
        {looks.map((look, index) => (
          <LookCard
            key={look.id}
            look={look}
            imageFetchPriority={index === 0 ? 'high' : 'auto'}
            imageLoading={index === 0 ? 'eager' : 'lazy'}
          />
        ))}
      </div>
    </section>
  );
}

function MainBanner({
  banner,
  loading = 'lazy',
  onNotice,
}: {
  banner: Banner;
  loading?: 'eager' | 'lazy';
  onNotice: (message: string) => void;
}) {
  const { currentPath, navigate } = useRouter();
  const imageUrl = normalizeAssetUrl(banner.image_url || banner.image_path);
  const action = getBannerAction(banner);
  const ctaLabel = getBannerCtaLabel(action);

  return (
    <button
      className="native-banner"
      type="button"
      aria-disabled={!action}
      onClick={() => void activateBanner(banner, navigate, onNotice, currentPath)}
    >
      {imageUrl ? (
        <span className="native-banner__image" aria-hidden="true">
          <img src={imageUrl} alt="" width={2000} height={1035} loading={loading} decoding="async" />
        </span>
      ) : <span className="banner-image-fallback" aria-hidden="true" />}
      {ctaLabel ? <span className="banner-cta">{ctaLabel}</span> : null}
    </button>
  );
}

function VerticalBannerGrid({ banners, onNotice }: { banners: Banner[]; onNotice: (message: string) => void }) {
  return (
    <section className="vertical-banner-grid" aria-label="Вертикальные акции">
      {banners.map((banner) => (
        <VerticalBannerCard banner={banner} key={banner.id} onNotice={onNotice} />
      ))}
    </section>
  );
}

function VerticalBannerCard({ banner, onNotice }: { banner: Banner; onNotice: (message: string) => void }) {
  const { currentPath, navigate } = useRouter();
  const imageUrl = normalizeAssetUrl(banner.image_url || banner.image_path);
  const action = getBannerAction(banner);
  const ctaLabel = getBannerCtaLabel(action);

  return (
    <button
      className="vertical-banner-card"
      type="button"
      aria-disabled={!action}
      onClick={() => void activateBanner(banner, navigate, onNotice, currentPath)}
    >
      <span className="vertical-banner-card__media" aria-hidden="true">
        {imageUrl ? (
          <img src={imageUrl} alt="" width={900} height={1600} loading="lazy" decoding="async" />
        ) : <span className="banner-image-fallback" />}
      </span>
      {ctaLabel ? <span className="banner-cta">{ctaLabel}</span> : null}
    </button>
  );
}

function BannerCarousel({ banners, onNotice }: { banners: Banner[]; onNotice: (message: string) => void }) {
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
      track.scrollTo({ left: track.clientWidth * nextIndex, behavior: getMotionAwareScrollBehavior() });
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
    track?.scrollTo({ left: track.clientWidth * index, behavior: getMotionAwareScrollBehavior() });
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
        {banners.map((banner, index) => (
          <div className="banner-carousel__slide" key={banner.id}>
            <MainBanner banner={banner} loading={index === 0 ? 'eager' : 'lazy'} onNotice={onNotice} />
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

async function activateBanner(
  banner: Banner,
  navigate: (to: string) => void,
  onNotice: (message: string) => void,
  currentPath: string,
) {
  const action = getBannerAction(banner);
  if (!action) {
    return;
  }

  void trackBannerClick(banner.id).catch(() => undefined);
  if (action.kind === 'copy') {
    try {
      await copyTextToClipboard(action.value);
      onNotice(`Промокод ${action.value} скопирован`);
    } catch {
      onNotice('Не удалось скопировать промокод');
    }
    return;
  }

  if (action.kind === 'internal') {
    navigate(action.value.startsWith('/product/') ? withReturnTo(action.value, currentPath) : action.value);
    return;
  }

  window.open(action.value, '_blank', 'noopener,noreferrer');
}
