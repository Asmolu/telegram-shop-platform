import React from 'react';
import { useAuth } from '../shared/auth/AuthProvider';
import { useRouter } from '../shared/router/RouterProvider';
import { EmptyState, TopBar } from '../shared/ui';
import { getTelegramThemeParams } from '../shared/telegram/webApp';
import { getUserDisplayName } from '../shared/utils/format';

export function ProfilePage() {
  const { navigate } = useRouter();
  const { clearToken, isAuthenticated, status, telegramUser, user } = useAuth();
  const theme = getTelegramThemeParams();
  const displayUser = user ?? telegramUser;
  const displayName = getUserDisplayName(displayUser);
  const username = displayUser?.username ? `@${displayUser.username}` : 'username не указан';

  return (
    <div className="page">
      <TopBar title="Личный кабинет" />

      {!isAuthenticated && status !== 'development' ? (
        <EmptyState title="Профиль недоступен" message="Откройте Mini App из Telegram." />
      ) : null}

      <section className="profile-card">
        <span className="profile-avatar">
          {telegramUser?.photo_url ? <img src={telegramUser.photo_url} alt="" /> : displayName.slice(0, 1).toUpperCase()}
        </span>
        <div>
          <h1>{displayName}</h1>
          <p>{username}</p>
        </div>
      </section>

      <section className="link-list">
        <button type="button" onClick={() => navigate('/cart?tab=orders')}>Мои заказы<span>›</span></button>
        <button type="button" onClick={() => navigate('/cart?tab=favorites')}>Избранное<span>›</span></button>
        <button type="button" onClick={() => navigate('/cart?tab=cart')}>Промокоды<span>›</span></button>
        <button type="button" onClick={() => navigate('/faq')}>FAQ<span>›</span></button>
        <button type="button" onClick={() => navigate('/faq')}>Поддержка<span>›</span></button>
      </section>

      <section className="settings-card">
        <h2>Настройки</h2>
        <div><span>Тема Telegram</span><strong>{theme.bg_color ? 'определена' : 'system'}</strong></div>
        <div><span>Уведомления</span><strong>скоро</strong></div>
        <div><span>Privacy / data policy</span><strong>скоро</strong></div>
      </section>

      <button className="secondary-button full-width" type="button" onClick={clearToken}>
        Очистить dev token
      </button>
    </div>
  );
}
