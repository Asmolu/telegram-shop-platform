import type React from 'react';
import type { User } from '../api';

export interface NavItem {
  path: string;
  label: string;
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
  const displayName = user
    ? [user.first_name, user.last_name].filter(Boolean).join(' ') || user.username || `User ${user.id}`
    : 'Token user';

  return (
    <div className="portal-layout">
      <aside className="sidebar">
        <div className="brand-block">
          <div className="brand-mark">TS</div>
          <div>
            <strong>Seller Portal</strong>
            <span>Telegram Shop</span>
          </div>
        </div>
        <nav className="sidebar-nav" aria-label="Seller navigation">
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
                {item.label}
              </button>
            );
          })}
        </nav>
        <div className="sidebar-account">
          <span>{displayName}</span>
          <small>{user?.role ?? 'JWT active'}</small>
          <button className="text-button" type="button" onClick={onLogout}>
            Logout
          </button>
        </div>
      </aside>
      <div className="workspace">
        <header className="topbar">
          <div>
            <p className="eyebrow">Seller Panel</p>
            <h1>{title}</h1>
          </div>
          <div className="topbar-profile">
            <span>{displayName}</span>
            <strong>{user?.role ?? 'TOKEN'}</strong>
          </div>
        </header>
        <main className="content-area">{children}</main>
      </div>
    </div>
  );
}
