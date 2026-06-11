import React from 'react';
import { getBanners, getCart, trackBannerClick, type Banner } from '../api';
import { useAuth } from '../auth/AuthProvider';
import { Link, useRouter } from '../router/RouterProvider';
import { getUserDisplayName } from '../utils/format';
import { normalizeAssetUrl } from '../utils/images';
import { copyTextToClipboard, getBannerAction, getBannerCtaLabel } from '../utils/banners';
import { SearchIcon } from './Icons';

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
  variant = 'default',
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
        <path d="M3.8 10.8 12 4l8.2 6.8v8.1a1.6 1.6 0 0 1-1.6 1.6h-4.1v-5.8h-5v5.8H5.4a1.6 1.6 0 0 1-1.6-1.6v-8.1Z" />
      </svg>
    );
  }

  if (name === 'grid') {
    return (
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <path d="M4.5 5.5A1.5 1.5 0 0 1 6 4h4v6H4.5V5.5Zm9.5-1.5h4a1.5 1.5 0 0 1 1.5 1.5V10H14V4ZM4.5 14H10v6H6a1.5 1.5 0 0 1-1.5-1.5V14Zm9.5 0h5.5v4.5A1.5 1.5 0 0 1 18 20h-4v-6Z" />
      </svg>
    );
  }

  if (name === 'search') {
    return <SearchIcon />;
  }

  if (name === 'cart') {
    return (
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <path d="M5.1 4H3V2h3.5l1 3h12.7l-1.6 8.1a2.3 2.3 0 0 1-2.2 1.9H9.7a2.3 2.3 0 0 1-2.2-1.7L5.1 4Zm4.8 16.5a1.8 1.8 0 1 1 0-3.6 1.8 1.8 0 0 1 0 3.6Zm6.8 0a1.8 1.8 0 1 1 0-3.6 1.8 1.8 0 0 1 0 3.6Z" />
      </svg>
    );
  }

  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M12 12.2a4.1 4.1 0 1 0 0-8.2 4.1 4.1 0 0 0 0 8.2Zm0 2.1c-4 0-7.2 2.1-7.2 4.8V20h14.4v-.9c0-2.7-3.2-4.8-7.2-4.8Z" />
    </svg>
  );
}
