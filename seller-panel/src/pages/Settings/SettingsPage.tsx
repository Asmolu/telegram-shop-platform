import { API_BASE_URL } from '../../shared/api';
import { clearStoredToken, getTokenStorageScope } from '../../shared/auth/tokenStorage';

interface PageProps {
  onAuthExpired: () => void;
}

export function SettingsPage({ onAuthExpired }: PageProps) {
  const tokenScope = getTokenStorageScope();

  function clearToken() {
    clearStoredToken();
    onAuthExpired();
  }

  return (
    <div className="page-stack">
      <section className="panel">
        <h2>API</h2>
        <dl className="settings-list">
          <div>
            <dt>Base URL</dt>
            <dd>
              <code>{API_BASE_URL}</code>
            </dd>
          </div>
          <div>
            <dt>Contract</dt>
            <dd>FastAPI OpenAPI under the configured API prefix.</dd>
          </div>
        </dl>
      </section>

      <section className="panel">
        <h2>Authentication</h2>
        <dl className="settings-list">
          <div>
            <dt>Mode</dt>
            <dd>Email/password seller auth with Telegram Bot 2 verification</dd>
          </div>
          <div>
            <dt>Token storage</dt>
            <dd>{tokenScope === 'local' ? 'This browser' : 'This tab'}</dd>
          </div>
        </dl>
        <button className="button button-secondary" type="button" onClick={clearToken}>
          Clear token and logout
        </button>
      </section>
    </div>
  );
}
