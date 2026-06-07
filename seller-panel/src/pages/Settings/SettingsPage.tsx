import { API_BASE_URL } from '../../shared/api';
import { clearStoredToken, getTokenStorageScope } from '../../shared/auth/tokenStorage';
import { useI18n } from '../../shared/i18n';

interface PageProps {
  onAuthExpired: () => void;
}

export function SettingsPage({ onAuthExpired }: PageProps) {
  const { t } = useI18n();
  const tokenScope = getTokenStorageScope();

  function clearToken() {
    clearStoredToken();
    onAuthExpired();
  }

  return (
    <div className="page-stack">
      <section className="panel">
        <h2>{t('settings.api')}</h2>
        <dl className="settings-list">
          <div>
            <dt>{t('settings.baseUrl')}</dt>
            <dd>
              <code>{API_BASE_URL}</code>
            </dd>
          </div>
          <div>
            <dt>{t('settings.contract')}</dt>
            <dd>{t('settings.contractDescription')}</dd>
          </div>
        </dl>
      </section>

      <section className="panel">
        <h2>{t('settings.authentication')}</h2>
        <dl className="settings-list">
          <div>
            <dt>{t('settings.mode')}</dt>
            <dd>{t('settings.authMode')}</dd>
          </div>
          <div>
            <dt>{t('settings.tokenStorage')}</dt>
            <dd>{tokenScope === 'local' ? t('auth.thisBrowser') : t('auth.thisTab')}</dd>
          </div>
        </dl>
        <button className="button button-secondary" type="button" onClick={clearToken}>
          {t('settings.clearToken')}
        </button>
      </section>
    </div>
  );
}
