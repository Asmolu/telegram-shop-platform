import React from 'react';
import {
  createCustomerNotificationStartLink,
  getCustomerNotificationSubscription,
  toApiErrorMessage,
  updateCustomerNotificationSubscription,
  type CustomerNotificationSubscription,
} from '../shared/api';
import { useAuth } from '../shared/auth/AuthProvider';
import { getAuthPath, useRouter } from '../shared/router/RouterProvider';
import { openTelegramLink } from '../shared/telegram/webApp';
import { EmptyState, TopBar } from '../shared/ui';
import { getUserDisplayName } from '../shared/utils/format';

export function ProfilePage() {
  const { currentPath, navigate } = useRouter();
  const { clearToken, isAuthenticated, isTelegram, status, telegramUser, user } = useAuth();
  const [subscription, setSubscription] =
    React.useState<CustomerNotificationSubscription | null>(null);
  const [notificationsLoading, setNotificationsLoading] = React.useState(false);
  const [notificationsSaving, setNotificationsSaving] = React.useState<string | null>(null);
  const [notificationsError, setNotificationsError] = React.useState<string | null>(null);
  const [notificationsHint, setNotificationsHint] = React.useState<string | null>(null);
  const displayUser = user ?? telegramUser;
  const displayName = getUserDisplayName(displayUser);
  const username = displayUser?.username
    ? `@${displayUser.username}`
    : 'Имя пользователя не указано';
  const notificationChatLabel = subscription?.telegram_username
    ? `@${subscription.telegram_username}`
    : subscription?.has_chat
      ? 'готов'
      : 'нужно открыть бот';

  React.useEffect(() => {
    if (!isAuthenticated) {
      setSubscription(null);
      return;
    }

    let cancelled = false;
    setNotificationsLoading(true);
    setNotificationsError(null);

    getCustomerNotificationSubscription()
      .then((state) => {
        if (!cancelled) {
          setSubscription(state);
        }
      })
      .catch((error) => {
        if (!cancelled) {
          setNotificationsError(toApiErrorMessage(error));
        }
      })
      .finally(() => {
        if (!cancelled) {
          setNotificationsLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [isAuthenticated]);

  async function handleNotificationToggle(
    field: 'service_opt_in' | 'marketing_opt_in',
    value: boolean,
  ) {
    setNotificationsSaving(field);
    setNotificationsError(null);
    setNotificationsHint(null);

    try {
      const nextState = await updateCustomerNotificationSubscription({ [field]: value });
      setSubscription(nextState);
      if (value && !nextState.has_chat) {
        setNotificationsHint('Сначала откройте бота, чтобы мы могли писать вам в Telegram.');
      }
    } catch (error) {
      setNotificationsError(toApiErrorMessage(error));
    } finally {
      setNotificationsSaving(null);
    }
  }

  async function handleOpenNotificationBot() {
    setNotificationsSaving('start-link');
    setNotificationsError(null);
    setNotificationsHint(null);

    try {
      const startLink = subscription?.bot_start_link
        ? subscription
        : await createCustomerNotificationStartLink();
      if (startLink.bot_start_link) {
        openTelegramLink(startLink.bot_start_link);
      } else {
        setNotificationsHint(`Откройте бот магазина и отправьте ${startLink.start_command}.`);
      }
    } catch (error) {
      setNotificationsError(toApiErrorMessage(error));
    } finally {
      setNotificationsSaving(null);
    }
  }

  return (
    <div className="page profile-page page--gradient-header">
      <TopBar title="Личный кабинет" variant="marketplace" />

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
          {telegramUser?.photo_url ? (
            <img src={telegramUser.photo_url} alt="" />
          ) : (
            displayName.slice(0, 1).toUpperCase()
          )}
        </span>
        <div>
          <h1>{displayName}</h1>
          <p>{username}</p>
        </div>
      </section>

      <section className="link-list">
        <button type="button" onClick={() => navigate('/cart?tab=orders')}>
          Мои заказы<span>›</span>
        </button>
        <button type="button" onClick={() => navigate('/cart?tab=favorites')}>
          Избранное<span>›</span>
        </button>
        <button type="button" onClick={() => navigate('/cart?tab=cart')}>
          Промокоды<span>›</span>
        </button>
        <button type="button" onClick={() => navigate('/faq')}>
          FAQ<span>›</span>
        </button>
        <button type="button" onClick={() => navigate('/faq')}>
          Поддержка<span>›</span>
        </button>
      </section>

      <section className="settings-card">
        <h2>Настройки</h2>
        <div>
          <span>Тема интерфейса</span>
          <strong>светлая</strong>
        </div>
        <div>
          <span>Данные и приватность</span>
          <strong>появятся позже</strong>
        </div>
      </section>

      {isAuthenticated ? (
        <section className="settings-card notification-settings-card">
          <div className="notification-settings-card__heading">
            <h2>Уведомления в Telegram</h2>
            <strong
              className={subscription?.has_chat ? 'status-text-success' : 'status-text-warning'}
            >
              {subscription?.has_chat ? 'подключены' : 'не подключены'}
            </strong>
          </div>

          {notificationsLoading ? <p className="muted-text">Загружаем настройки...</p> : null}
          {notificationsError ? <p className="form-error">{notificationsError}</p> : null}
          {notificationsHint ? (
            <p className="inline-notice inline-notice--info">{notificationsHint}</p>
          ) : null}

          <div className="notification-row">
            <span>Telegram-чат</span>
            <strong>{notificationChatLabel}</strong>
          </div>

          <label className="toggle-setting">
            <span>
              <strong>Заказы и сервисные сообщения</strong>
              <small>Статусы заказов и важные сообщения магазина.</small>
            </span>
            <input
              checked={Boolean(subscription?.service_opt_in)}
              disabled={notificationsLoading || notificationsSaving !== null}
              type="checkbox"
              onChange={(event) =>
                handleNotificationToggle('service_opt_in', event.target.checked)
              }
            />
          </label>

          <label className="toggle-setting">
            <span>
              <strong>Рекламные предложения</strong>
              <small>Скидки и подборки, только если вы сами включите.</small>
            </span>
            <input
              checked={Boolean(subscription?.marketing_opt_in)}
              disabled={notificationsLoading || notificationsSaving !== null}
              type="checkbox"
              onChange={(event) =>
                handleNotificationToggle('marketing_opt_in', event.target.checked)
              }
            />
          </label>

          {!subscription?.has_chat ? (
            <button
              className="primary-button full-width"
              disabled={notificationsSaving !== null}
              type="button"
              onClick={handleOpenNotificationBot}
            >
              {notificationsSaving === 'start-link' ? 'Открываем...' : 'Открыть бот'}
            </button>
          ) : null}

          <p className="muted-text">
            Если отправить боту /stop, все сообщения выключатся до нового /start.
          </p>
        </section>
      ) : null}

      {!isTelegram ? (
        <button className="secondary-button full-width" type="button" onClick={clearToken}>
          Сбросить тестовый вход
        </button>
      ) : null}
    </div>
  );
}
