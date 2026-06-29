import React from 'react';
import {
  createCustomerNotificationStartLink,
  getCustomerNotificationSubscription,
  recordCustomerNotificationWriteAccess,
  toApiErrorMessage,
  updateCustomerNotificationSubscription,
  type CustomerNotificationSubscription,
} from '../shared/api';
import { useAuth } from '../shared/auth/AuthProvider';
import { getAuthPath, useRouter, withReturnTo } from '../shared/router/RouterProvider';
import { SUPPORT_TELEGRAM_URL, openTelegramLink, requestTelegramWriteAccess } from '../shared/telegram/webApp';
import { useTheme } from '../shared/theme/ThemeProvider';
import { EmptyState, TopBar } from '../shared/ui';
import { getUserDisplayName } from '../shared/utils/format';

const NOTIFICATION_WRITE_ACCESS_SOURCE = 'mini_app_request_write_access';

function areServiceNotificationsAvailable(subscription: CustomerNotificationSubscription | null) {
  if (!subscription) {
    return false;
  }
  if (typeof subscription.service_notifications_available === 'boolean') {
    return subscription.service_notifications_available;
  }
  return Boolean(subscription.has_chat && subscription.service_opt_in && !subscription.blocked_at);
}

export function ProfilePage() {
  const { currentPath, navigate } = useRouter();
  const { clearToken, isAuthenticated, isTelegram, status, telegramUser, user } = useAuth();
  const { theme, themePreference, setTheme } = useTheme();
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
  const serviceNotificationsAvailable = areServiceNotificationsAvailable(subscription);
  const notificationChatLabel = subscription?.telegram_username
    ? `@${subscription.telegram_username}`
    : serviceNotificationsAvailable
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
      if (value && !areServiceNotificationsAvailable(nextState)) {
        setNotificationsHint('Сначала откройте бота, чтобы мы могли писать вам в Telegram.');
      }
    } catch (error) {
      setNotificationsError(toApiErrorMessage(error));
    } finally {
      setNotificationsSaving(null);
    }
  }

  async function handleAllowNotificationWriteAccess() {
    setNotificationsSaving('write-access');
    setNotificationsError(null);
    setNotificationsHint(null);

    try {
      const result = await requestTelegramWriteAccess();
      if (result === 'granted') {
        const nextState = await recordCustomerNotificationWriteAccess({
          granted: true,
          source: NOTIFICATION_WRITE_ACCESS_SOURCE,
        });
        setSubscription(nextState);
        setNotificationsHint(
          areServiceNotificationsAvailable(nextState)
            ? 'Уведомления о заказах включены'
            : 'Откройте Bot 1, чтобы получать статусы заказа.',
        );
        return;
      }

      if (result === 'denied') {
        const nextState = await recordCustomerNotificationWriteAccess({
          granted: false,
          source: NOTIFICATION_WRITE_ACCESS_SOURCE,
        }).catch(() => null);
        if (nextState) {
          setSubscription(nextState);
        }
      }
      setNotificationsHint('Откройте Bot 1, чтобы получать статусы заказа.');
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
        <button type="button" onClick={() => navigate('/profile/personal-data')}>
          Личные данные<span>›</span>
        </button>
        <button type="button" onClick={() => navigate('/cart?tab=orders')}>
          Мои заказы<span>›</span>
        </button>
        <button type="button" onClick={() => navigate('/cart?tab=favorites')}>
          Избранное<span>›</span>
        </button>
        <button type="button" onClick={() => navigate('/cart?tab=cart')}>
          Промокоды<span>›</span>
        </button>
        <button type="button" onClick={() => navigate(withReturnTo('/faq', currentPath))}>
          FAQ<span>›</span>
        </button>
        <button type="button" onClick={() => openTelegramLink(SUPPORT_TELEGRAM_URL)}>
          Поддержка<span>›</span>
        </button>
      </section>

      <section className="settings-card">
        <h2>Настройки</h2>
        <label className="toggle-setting">
          <span>
            <strong>Тема интерфейса</strong>
            <small>
              {themePreference === 'auto'
                ? `Авто · ${theme === 'dark' ? 'тёмная' : 'светлая'}`
                : theme === 'dark'
                  ? 'Тёмная'
                  : 'Светлая'}
            </small>
          </span>
          <div className="segmented-control theme-mode-control" aria-label="Режим темы">
            {[
              ['auto', 'Авто'],
              ['light', 'Свет'],
              ['dark', 'Тьма'],
            ].map(([value, label]) => (
              <button
                className={themePreference === value ? 'is-selected' : ''}
                key={value}
                type="button"
                onClick={() => setTheme(value as 'auto' | 'light' | 'dark')}
              >
                {label}
              </button>
            ))}
          </div>
        </label>
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
              className={serviceNotificationsAvailable ? 'status-text-success' : 'status-text-warning'}
            >
              {serviceNotificationsAvailable ? 'подключены' : 'не подключены'}
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
              <strong>Акции и скидки</strong>
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

          {!serviceNotificationsAvailable ? (
            <div className="notification-profile-actions">
              <button
                className="primary-button full-width"
                disabled={notificationsSaving !== null}
                type="button"
                onClick={handleAllowNotificationWriteAccess}
              >
                {notificationsSaving === 'write-access' ? 'Запрашиваем...' : 'Разрешить уведомления'}
              </button>
              <button
                className="secondary-button full-width"
                disabled={notificationsSaving !== null}
                type="button"
                onClick={handleOpenNotificationBot}
              >
                {notificationsSaving === 'start-link' ? 'Открываем...' : 'Открыть бот'}
              </button>
            </div>
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
