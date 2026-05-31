import React from 'react';
import { useAuth } from '../shared/auth/AuthProvider';
import { useRouter } from '../shared/router/RouterProvider';
import { ProductGridSkeleton } from '../shared/ui';
import { getTelegramBotUrl } from '../shared/telegram/webApp';
import { toApiErrorMessage } from '../shared/api';

export function LaunchPage() {
  const { status, error, isTelegram, loginWithToken, retryTelegramAuth } = useAuth();
  const { navigate } = useRouter();
  const [token, setToken] = React.useState('');
  const [tokenError, setTokenError] = React.useState<string | null>(null);
  const botUrl = getTelegramBotUrl();

  React.useEffect(() => {
    if (status === 'authenticated') {
      const timer = window.setTimeout(() => navigate('/main', { replace: true }), 350);
      return () => window.clearTimeout(timer);
    }

    return undefined;
  }, [navigate, status]);

  async function submitDevToken(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setTokenError(null);
    try {
      await loginWithToken(token.trim());
      navigate('/main', { replace: true });
    } catch (loginError) {
      setTokenError(toApiErrorMessage(loginError));
    }
  }

  const isLoading = status === 'booting' || status === 'authenticated';

  return (
    <div className="launch-screen">
      <div className="launch-brand">
        <div className="logo-mark">G</div>
        <strong>Gadji Store</strong>
        <span>Загружаем магазин...</span>
      </div>

      {isLoading ? <ProductGridSkeleton /> : null}

      {status === 'error' ? (
        <section className="auth-card">
          <h1>Не удалось открыть приложение через Telegram</h1>
          <p>{error ?? 'Проверьте, что Mini App открыт из Telegram.'}</p>
          <div className="button-row">
            <button className="primary-button" type="button" onClick={() => void retryTelegramAuth()}>
              Повторить
            </button>
            {botUrl ? (
              <a className="secondary-button" href={botUrl}>
                Open in Telegram
              </a>
            ) : null}
          </div>
        </section>
      ) : null}

      {status === 'development' && isTelegram ? (
        <section className="auth-card">
          <h1>Не удалось получить Telegram auth</h1>
          <p>Откройте Mini App через кнопку бота и попробуйте снова.</p>
          <div className="button-row">
            <button className="primary-button" type="button" onClick={() => void retryTelegramAuth()}>
              Повторить
            </button>
          </div>
        </section>
      ) : null}

      {status === 'development' && !isTelegram ? (
        <section className="auth-card">
          <h1>Development mode</h1>
          <p>Приложение открыто вне Telegram. Каталог можно смотреть без входа, а для корзины и заказов нужен JWT.</p>
          <div className="button-row">
            {botUrl ? (
              <a className="primary-button" href={botUrl}>
                Open in Telegram
              </a>
            ) : null}
            <button className="secondary-button" type="button" onClick={() => navigate('/main', { replace: true })}>
              Перейти к товарам
            </button>
          </div>
          <form className="dev-token-form" onSubmit={submitDevToken}>
            <label htmlFor="dev-token">JWT для локального теста</label>
            <textarea
              id="dev-token"
              value={token}
              onChange={(event) => setToken(event.target.value)}
              placeholder="Вставьте готовый access token"
              rows={3}
            />
            {tokenError ? <p className="form-error">{tokenError}</p> : null}
            <button className="primary-button" type="submit" disabled={!token.trim()}>
              Использовать токен
            </button>
          </form>
        </section>
      ) : null}
    </div>
  );
}
