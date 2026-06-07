import { FormEvent, useState } from 'react';
import { setStoredToken, type TokenStorageScope } from '../../shared/auth/tokenStorage';
import { useI18n } from '../../shared/i18n';

interface DevTokenLoginPageProps {
  authError: string | null;
  onTokenSaved: () => void;
}

export function DevTokenLoginPage({ authError, onTokenSaved }: DevTokenLoginPageProps) {
  const { t } = useI18n();
  const [token, setToken] = useState('');
  const [scope, setScope] = useState<TokenStorageScope>('session');
  const [error, setError] = useState<string | null>(null);

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const cleanToken = token.trim();

    if (!cleanToken) {
      setError(t('auth.pasteJwt'));
      return;
    }

    setStoredToken(cleanToken, scope);
    onTokenSaved();
  }

  return (
    <main className="login-page">
      <section className="login-card">
        <p className="eyebrow">{t('auth.devTitle')}</p>
        <h1>{t('app.brand')}</h1>
        <p>{t('auth.devDescription')}</p>
        {authError ? <div className="form-error">{authError}</div> : null}
        {error ? <div className="form-error">{error}</div> : null}
        <form onSubmit={handleSubmit}>
          <label className="field">
            <span>{t('auth.jwtToken')}</span>
            <textarea
              rows={6}
              value={token}
              onChange={(event) => setToken(event.target.value)}
              placeholder={t('auth.jwtPlaceholder')}
            />
          </label>
          <fieldset className="segmented-field">
            <legend>{t('auth.storage')}</legend>
            <label>
              <input
                checked={scope === 'session'}
                name="token-scope"
                type="radio"
                onChange={() => setScope('session')}
              />
              {t('auth.thisTab')}
            </label>
            <label>
              <input
                checked={scope === 'local'}
                name="token-scope"
                type="radio"
                onChange={() => setScope('local')}
              />
              {t('auth.thisBrowser')}
            </label>
          </fieldset>
          <button className="button button-primary button-wide" type="submit">
            {t('auth.continue')}
          </button>
        </form>
      </section>
    </main>
  );
}
