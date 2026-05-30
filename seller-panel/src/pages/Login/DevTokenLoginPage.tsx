import { FormEvent, useState } from 'react';
import { setStoredToken, type TokenStorageScope } from '../../shared/auth/tokenStorage';

interface DevTokenLoginPageProps {
  authError: string | null;
  onTokenSaved: () => void;
}

export function DevTokenLoginPage({ authError, onTokenSaved }: DevTokenLoginPageProps) {
  const [token, setToken] = useState('');
  const [scope, setScope] = useState<TokenStorageScope>('session');
  const [error, setError] = useState<string | null>(null);

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const cleanToken = token.trim();

    if (!cleanToken) {
      setError('Paste a JWT access token to continue.');
      return;
    }

    setStoredToken(cleanToken, scope);
    onTokenSaved();
  }

  return (
    <main className="login-page">
      <section className="login-card">
        <p className="eyebrow">Temporary development auth</p>
        <h1>Seller Portal</h1>
        <p>
          The backend currently exposes Telegram JWT auth, not a seller password login. Paste a
          seller or admin access token here while the real login screen is pending.
        </p>
        {authError ? <div className="form-error">{authError}</div> : null}
        {error ? <div className="form-error">{error}</div> : null}
        <form onSubmit={handleSubmit}>
          <label className="field">
            <span>JWT access token</span>
            <textarea
              rows={6}
              value={token}
              onChange={(event) => setToken(event.target.value)}
              placeholder="Paste Bearer token without the Bearer prefix"
            />
          </label>
          <fieldset className="segmented-field">
            <legend>Storage</legend>
            <label>
              <input
                checked={scope === 'session'}
                name="token-scope"
                type="radio"
                onChange={() => setScope('session')}
              />
              This tab
            </label>
            <label>
              <input
                checked={scope === 'local'}
                name="token-scope"
                type="radio"
                onChange={() => setScope('local')}
              />
              This browser
            </label>
          </fieldset>
          <button className="button button-primary button-wide" type="submit">
            Continue
          </button>
        </form>
      </section>
    </main>
  );
}
