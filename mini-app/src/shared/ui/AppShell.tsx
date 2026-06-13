import React from 'react';
import { getBanners, getCart, trackBannerClick, type Banner } from '../api';
import { useAuth } from '../auth/AuthProvider';
import { Link, useRouter } from '../router/RouterProvider';
import { getUserDisplayName } from '../utils/format';
import { normalizeAssetUrl } from '../utils/images';
import { copyTextToClipboard, getBannerAction, getBannerCtaLabel } from '../utils/banners';

const navItems = [
  { to: '/main', label: 'Лента', icon: 'home', match: ['/main', '/'] },
  { to: '/categories', label: 'Категории', icon: 'grid', match: ['/categories', '/category'] },
  { to: '/search', label: 'Поиск', icon: 'search', match: ['/search', '/search/results'] },
  { to: '/cart?tab=cart', label: 'Корзина', icon: 'cart', match: ['/cart', '/checkout', '/order-success'] },
  { to: '/profile', label: 'Профиль', icon: 'profile', match: ['/profile'] },
] as const;

const AGGRESSIVE_POPUP_SESSION_KEY = 'telegram_shop_aggressive_popup_dismissed';
const POPUP_SESSION_KEY = 'telegram_shop_popup_dismissed';

function isActive(pathname: string, item: (typeof navItems)[number]) {
  return item.match.some((path) => pathname === path || pathname.startsWith(`${path}/`));
}

export function TopBar({
  title,
  onBack,
  right,
  variant = 'marketplace',
}: {
  title: string;
  onBack?: () => void;
  right?: React.ReactNode;
  variant?: 'default' | 'marketplace';
}) {
  return (
    <header className={`top-bar ${variant === 'marketplace' ? 'top-bar--marketplace' : ''}`}>
      <div className="top-bar__left">
        {onBack ? (
          <button className="icon-button" type="button" aria-label="Назад" onClick={onBack}>
            ‹
          </button>
        ) : null}
        <h1>{title}</h1>
      </div>
      {right ? <div className="top-bar__right">{right}</div> : null}
    </header>
  );
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const { currentPath, pathname, navigate } = useRouter();
  const { isAuthenticated, telegramUser, user } = useAuth();
  const [cartCount, setCartCount] = React.useState(0);
  const [aggressiveBanners, setAggressiveBanners] = React.useState<Banner[]>([]);
  const [popupBanners, setPopupBanners] = React.useState<Banner[]>([]);
  const [showAggressivePopup, setShowAggressivePopup] = React.useState(false);
  const [showPopup, setShowPopup] = React.useState(false);

  React.useEffect(() => {
    let cancelled = false;

    async function loadCartCount() {
      if (!isAuthenticated) {
        setCartCount(0);
        return;
      }

      try {
        const cart = await getCart();
        if (!cancelled) {
          setCartCount(cart.quantity_total);
        }
      } catch {
        if (!cancelled) {
          setCartCount(0);
        }
      }
    }

    void loadCartCount();
    const onCartUpdated = () => void loadCartCount();
    window.addEventListener('miniapp:cart-updated', onCartUpdated);
    return () => {
      cancelled = true;
      window.removeEventListener('miniapp:cart-updated', onCartUpdated);
    };
  }, [isAuthenticated]);

  React.useEffect(() => {
    let cancelled = false;

    async function loadBannerPopups() {
      try {
        const result = await getBanners();
        if (cancelled) {
          return;
        }

        const entryBanners = result.items.filter((banner) => banner.display_type === 'aggressive_popup');
        const modalBanners = result.items.filter((banner) => banner.display_type === 'popup');
        if (
          window.sessionStorage.getItem(AGGRESSIVE_POPUP_SESSION_KEY) !== '1'
          && entryBanners.length > 0
        ) {
          setAggressiveBanners(entryBanners);
          setShowAggressivePopup(true);
        }
        if (window.sessionStorage.getItem(POPUP_SESSION_KEY) !== '1' && modalBanners.length > 0) {
          setPopupBanners(modalBanners);
          setShowPopup(true);
        }
      } catch {
        if (!cancelled) {
          setAggressiveBanners([]);
          setPopupBanners([]);
          setShowAggressivePopup(false);
          setShowPopup(false);
        }
      }
    }

    void loadBannerPopups();
    return () => {
      cancelled = true;
    };
  }, []);

  function closeAggressivePopup() {
    window.sessionStorage.setItem(AGGRESSIVE_POPUP_SESSION_KEY, '1');
    setShowAggressivePopup(false);
  }

  function closePopup() {
    window.sessionStorage.setItem(POPUP_SESSION_KEY, '1');
    setShowPopup(false);
  }

  const profilePhoto = telegramUser?.photo_url;
  const profileLabel = getUserDisplayName(user ?? telegramUser);

  return (
    <div className="mini-app-frame">
      <main className="app-content">{children}</main>
      <FloatingOrderHelp currentPath={currentPath} onOpen={() => navigate('/faq?topic=order')} />
      {showAggressivePopup && aggressiveBanners.length > 0 ? (
        <BannerPopup
          banners={aggressiveBanners}
          variant="aggressive"
          onClose={closeAggressivePopup}
          onNavigate={(to) => {
            closeAggressivePopup();
            navigate(to);
          }}
        />
      ) : null}
      {!showAggressivePopup && showPopup && popupBanners.length > 0 ? (
        <BannerPopup
          banners={popupBanners}
          variant="popup"
          onClose={closePopup}
          onNavigate={(to) => {
            closePopup();
            navigate(to);
          }}
        />
      ) : null}
      <nav className="bottom-nav" aria-label="Основная навигация">
        {navItems.map((item) => {
          const active = isActive(pathname, item);
          const isCart = item.label === 'Корзина';
          const isProfile = item.label === 'Профиль';

          return (
            <Link className={`bottom-nav__item ${active ? 'is-active' : ''}`} to={item.to} key={item.to}>
              <span className="bottom-nav__icon" aria-hidden="true">
                {isProfile && profilePhoto ? (
                  <img src={profilePhoto} alt="" />
                ) : (
                  <NavIcon name={item.icon} />
                )}
                {isCart && cartCount > 0 ? <span className="cart-badge">{cartCount > 99 ? '99+' : cartCount}</span> : null}
              </span>
              <span>{item.label}</span>
              {isProfile ? <span className="sr-only">{profileLabel}</span> : null}
            </Link>
          );
        })}
      </nav>
    </div>
  );
}

function FloatingOrderHelp({
  currentPath,
  onOpen,
}: {
  currentPath: string;
  onOpen: () => void;
}) {
  const hidden = currentPath.startsWith('/faq')
    || currentPath.startsWith('/cart')
    || currentPath.startsWith('/checkout')
    || currentPath.startsWith('/product/')
    || currentPath.startsWith('/order-success/')
    || currentPath.startsWith('/profile');

  if (hidden) {
    return null;
  }

  return (
    <button className="floating-help-widget" type="button" onClick={onOpen}>
      <span aria-hidden="true">?</span>
      <strong>Как совершить заказ?</strong>
    </button>
  );
}

function BannerPopup({
  banners,
  variant,
  onClose,
  onNavigate,
}: {
  banners: Banner[];
  variant: 'aggressive' | 'popup';
  onClose: () => void;
  onNavigate: (to: string) => void;
}) {
  const trackRef = React.useRef<HTMLDivElement | null>(null);
  const [activeIndex, setActiveIndex] = React.useState(0);
  const interactionPauseUntil = React.useRef(0);
  const activeBanner = banners[activeIndex] ?? banners[0];
  const bannerAction = getBannerAction(activeBanner);
  const ctaLabel = getBannerCtaLabel(bannerAction);
  const hasMultipleBanners = banners.length > 1;
  const [copyNotice, setCopyNotice] = React.useState<string | null>(null);

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
      if (Date.now() < interactionPauseUntil.current) {
        return;
      }

      const track = trackRef.current;
      if (!track) {
        return;
      }

      const nextIndex = (activeIndex + 1) % banners.length;
      track.scrollTo({ left: track.clientWidth * nextIndex, behavior: 'smooth' });
      setActiveIndex(nextIndex);
    }, 4200);

    return () => window.clearInterval(timer);
  }, [activeIndex, banners.length, hasMultipleBanners]);

  function pauseAutoplay() {
    interactionPauseUntil.current = Date.now() + 7000;
  }

  function chooseSlide(index: number) {
    const track = trackRef.current;
    pauseAutoplay();
    track?.scrollTo({ left: track.clientWidth * index, behavior: 'smooth' });
    setActiveIndex(index);
  }

  async function handleBannerAction() {
    if (!bannerAction) {
      return;
    }

    void trackBannerClick(activeBanner.id).catch(() => undefined);

    if (bannerAction.kind === 'copy') {
      try {
        await copyTextToClipboard(bannerAction.value);
        setCopyNotice(`Промокод ${bannerAction.value} скопирован`);
      } catch {
        setCopyNotice('Не удалось скопировать промокод');
      }
      return;
    }

    if (bannerAction.kind === 'internal') {
      onNavigate(bannerAction.value);
      return;
    }

    onClose();
    window.open(bannerAction.value, '_blank', 'noopener,noreferrer');
  }

  return (
    <div
      className={`aggressive-popup aggressive-popup--${variant}`}
      role="dialog"
      aria-modal="true"
      aria-label="Акция"
    >
      <div className="aggressive-popup__backdrop" onClick={onClose} />
      <section className="aggressive-popup__card">
        <button className="aggressive-popup__close" type="button" aria-label="Закрыть" onClick={onClose}>
          ×
        </button>
        <div className="aggressive-popup__media" onPointerDown={pauseAutoplay}>
          <div className="aggressive-popup__track" ref={trackRef} onScroll={updateActiveIndex}>
            {banners.map((banner) => {
              const imageUrl = normalizeAssetUrl(banner.image_url || banner.image_path);
              return (
                <div className="aggressive-popup__slide" key={banner.id}>
                  {imageUrl ? <img src={imageUrl} alt="" /> : <span className="banner-image-fallback" />}
                </div>
              );
            })}
          </div>
        </div>
        {hasMultipleBanners ? (
          <div className="banner-dots banner-dots--popup" aria-label="Баннеры">
            {banners.map((banner, index) => (
              <button
                className={activeIndex === index ? 'is-active' : ''}
                key={banner.id}
                type="button"
                aria-label={`Баннер ${index + 1}`}
                onClick={() => chooseSlide(index)}
              />
            ))}
          </div>
        ) : null}
        {copyNotice ? <div className="banner-copy-toast">{copyNotice}</div> : null}
        {ctaLabel ? (
          <button className="banner-popup-cta" type="button" onClick={() => void handleBannerAction()}>
            {ctaLabel}
          </button>
        ) : null}
      </section>
    </div>
  );
}

function NavIcon({ name }: { name: (typeof navItems)[number]['icon'] }) {
  if (name === 'home') {
    return (
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <path d="M3.5 10.2 12 3l8.5 7.2v8.1a2.2 2.2 0 0 1-2.2 2.2H5.7a2.2 2.2 0 0 1-2.2-2.2v-8.1Z" />
        <path d="M7.2 11h1.7M11.2 11h5.6M7.2 14.5h1.7M11.2 14.5h5.6M8.2 18h7.6" />
      </svg>
    );
  }

  if (name === 'grid') {
    return (
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <rect x="3.5" y="3.5" width="17" height="17" rx="4" />
        <rect x="7" y="7" width="3" height="3" rx=".6" />
        <rect x="14" y="7" width="3" height="3" rx=".6" />
        <rect x="7" y="14" width="3" height="3" rx=".6" />
        <rect x="14" y="14" width="3" height="3" rx=".6" />
      </svg>
    );
  }

  if (name === 'search') {
    return (
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <circle cx="10.5" cy="10.5" r="6.4" />
        <path d="m15.3 15.3 4.5 4.5" />
      </svg>
    );
  }

  if (name === 'cart') {
    return (
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <path d="M3.2 4h2.6l2 10.1a2 2 0 0 0 2 1.6h6.7a2 2 0 0 0 1.9-1.5L20.7 7H6.4" />
        <circle cx="10" cy="19.3" r="1.2" />
        <circle cx="17" cy="19.3" r="1.2" />
      </svg>
    );
  }

  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <circle cx="12" cy="8.2" r="4" />
      <path d="M4.8 20c.4-4 3.1-6.3 7.2-6.3s6.8 2.3 7.2 6.3" />
    </svg>
  );
}
