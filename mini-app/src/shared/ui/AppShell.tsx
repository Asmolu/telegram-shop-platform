import React from 'react';
import { getCart } from '../api';
import { useAuth } from '../auth/AuthProvider';
import { Link, useRouter } from '../router/RouterProvider';
import { getUserDisplayName } from '../utils/format';

const navItems = [
  { to: '/main', label: 'Лента', icon: '⌂', match: ['/main', '/'] },
  { to: '/categories', label: 'Категории', icon: '▦', match: ['/categories'] },
  { to: '/search', label: 'Поиск', icon: '⌕', match: ['/search', '/search/results'] },
  { to: '/cart?tab=cart', label: 'Корзина', icon: '◴', match: ['/cart', '/checkout', '/order-success'] },
  { to: '/profile', label: 'Профиль', icon: '◌', match: ['/profile'] },
];

function isActive(pathname: string, item: (typeof navItems)[number]) {
  return item.match.some((path) => pathname === path || pathname.startsWith(`${path}/`));
}

export function TopBar({
  title,
  onBack,
  right,
}: {
  title: string;
  onBack?: () => void;
  right?: React.ReactNode;
}) {
  return (
    <header className="top-bar">
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
  const { pathname } = useRouter();
  const { isAuthenticated, telegramUser, user } = useAuth();
  const [cartCount, setCartCount] = React.useState(0);

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

  const profilePhoto = telegramUser?.photo_url;
  const profileLabel = getUserDisplayName(user ?? telegramUser);

  return (
    <div className="mini-app-frame">
      <main className="app-content">{children}</main>
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
                  item.icon
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
