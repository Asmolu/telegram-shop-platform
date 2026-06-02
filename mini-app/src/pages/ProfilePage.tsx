import React from 'react';
import { useAuth } from '../shared/auth/AuthProvider';
import { getAuthPath, useRouter } from '../shared/router/RouterProvider';
import { EmptyState, TopBar } from '../shared/ui';
import { getTelegramThemeParams } from '../shared/telegram/webApp';
import { getUserDisplayName } from '../shared/utils/format';

export function ProfilePage() {
  const { currentPath, navigate } = useRouter();
  const { clearToken, isAuthenticated, isTelegram, status, telegramUser, user } = useAuth();
  const theme = getTelegramThemeParams();
  const displayUser = user ?? telegramUser;
  const displayName = getUserDisplayName(displayUser);
  const username = displayUser?.username ? `@${displayUser.username}` : 'Имя пользователя не указано';

  return (
    <div className="page profile-page">
      <TopBar title="Личный кабинет" />

      {!isAuthenticated && status !== 'development' ? (
        <EmptyState
          title="Профиль недоступен"
          message="Откройте приложение через Telegram, чтобы увидеть личные данные."
          actionLabel="Войти"
          onAction={() => navigate(getAuthPath(currentPath))}
        />
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
        <div><span>Тема Telegram</span><strong>{theme.bg_color ? 'определена' : 'по умолчанию'}</strong></div>
        <div><span>Уведомления</span><strong>появятся позже</strong></div>
        <div><span>Данные и приватность</span><strong>появятся позже</strong></div>
      </section>

      {!isTelegram ? (
        <button className="secondary-button full-width" type="button" onClick={clearToken}>
          Сбросить тестовый вход
        </button>
      ) : null}
    </div>
  );
}
