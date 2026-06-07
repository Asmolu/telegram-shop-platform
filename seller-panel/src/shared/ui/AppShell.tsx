import type React from 'react';
import type { User } from '../api';
import { useI18n } from '../i18n';

export interface NavItem {
  path: string;
  labelKey: string;
}

interface AppShellProps {
  navItems: NavItem[];
  currentPath: string;
  title: string;
  user: User | null;
  children: React.ReactNode;
  onNavigate: (path: string) => void;
  onLogout: () => void;
}

export function AppShell({
  navItems,
  currentPath,
  title,
  user,
  children,
  onNavigate,
  onLogout,
}: AppShellProps) {
  const { language, setLanguage, t } = useI18n();
  const displayName = user
    ? [user.first_name, user.last_name].filter(Boolean).join(' ') ||
      user.username ||
      `${t('common.user')} ${user.id}`
    : t('app.tokenUser');

  return (
    <div className="portal-layout">
      <aside className="sidebar">
        <div className="brand-block">
          <div className="brand-mark">TS</div>
          <div>
            <strong>{t('app.brand')}</strong>
            <span>{t('app.product')}</span>
          </div>
        </div>
        <nav className="sidebar-nav" aria-label={t('app.navigation')}>
          {navItems.map((item) => {
            const active =
              currentPath === item.path ||
              (item.path !== '/dashboard' && currentPath.startsWith(item.path));

            return (
              <button
                className={`nav-link ${active ? 'nav-link-active' : ''}`}
                key={item.path}
                type="button"
                onClick={() => onNavigate(item.path)}
              >
                {t(item.labelKey)}
              </button>
            );
          })}
        </nav>
        <div className="sidebar-account">
          <span>{displayName}</span>
          <small>{user?.role ?? t('app.jwtActive')}</small>
          <button className="text-button" type="button" onClick={onLogout}>
            {t('app.logout')}
          </button>
        </div>
      </aside>
      <div className="workspace">
        <header className="topbar">
          <div>
            <p className="eyebrow">{t('app.eyebrow')}</p>
            <h1>{title}</h1>
          </div>
          <div className="topbar-actions">
            <div className="language-switcher" aria-label={t('app.language')}>
              <button
                className={language === 'ru' ? 'language-active' : ''}
                type="button"
                onClick={() => setLanguage('ru')}
              >
                {t('app.language.ru')}
              </button>
              <button
                className={language === 'en' ? 'language-active' : ''}
                type="button"
                onClick={() => setLanguage('en')}
              >
                {t('app.language.en')}
              </button>
            </div>
            <div className="topbar-profile">
              <span>{displayName}</span>
              <strong>{user?.role ?? 'TOKEN'}</strong>
            </div>
          </div>
        </header>
        <main className="content-area">{children}</main>
      </div>
    </div>
  );
}
