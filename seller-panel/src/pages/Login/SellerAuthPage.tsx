import { FormEvent, useState } from 'react';
import { ApiError, api } from '../../shared/api';
import type { SellerRegistrationStartResponse } from '../../shared/api';
import { setStoredToken, type TokenStorageScope } from '../../shared/auth/tokenStorage';
import { languageToLocale, useI18n } from '../../shared/i18n';
import { DevTokenLoginPage } from './DevTokenLoginPage';

interface SellerAuthPageProps {
  authError: string | null;
  onTokenSaved: () => void;
}

type AuthTab = 'login' | 'register';

const EMAIL_RE = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;
const TELEGRAM_RE = /^@?[A-Za-z0-9_]{5,32}$/;

export function SellerAuthPage({ authError, onTokenSaved }: SellerAuthPageProps) {
  const { language, t } = useI18n();
  const [activeTab, setActiveTab] = useState<AuthTab>('login');
  const [storageScope, setStorageScope] = useState<TokenStorageScope>('session');
  const [loginEmail, setLoginEmail] = useState('');
  const [loginPassword, setLoginPassword] = useState('');
  const [registerEmail, setRegisterEmail] = useState('');
  const [registerPassword, setRegisterPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [telegramUsername, setTelegramUsername] = useState('');
  const [registration, setRegistration] = useState<SellerRegistrationStartResponse | null>(null);
  const [verificationCode, setVerificationCode] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [loadingAction, setLoadingAction] = useState<string | null>(null);
  const [showDevTokenLogin, setShowDevTokenLogin] = useState(false);

  if (import.meta.env.DEV && showDevTokenLogin) {
    return <DevTokenLoginPage authError={authError} onTokenSaved={onTokenSaved} />;
  }

  async function handleLogin(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setSuccess(null);
    const validationError = validateLogin();
    if (validationError) {
      setError(validationError);
      return;
    }

    setLoadingAction('login');
    try {
      const response = await api.sellerAuth.login({
        email: loginEmail.trim(),
        password: loginPassword,
      });
      setStoredToken(response.access_token, storageScope);
      onTokenSaved();
    } catch (requestError) {
      setError(formatApiError(requestError, t('auth.loginFailed')));
    } finally {
      setLoadingAction(null);
    }
  }

  async function handleStartRegistration(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setSuccess(null);
    const validationError = validateRegistration();
    if (validationError) {
      setError(validationError);
      return;
    }

    setLoadingAction('start-registration');
    try {
      const response = await api.sellerAuth.startRegistration({
        email: registerEmail.trim(),
        password: registerPassword,
        telegram_username: telegramUsername.trim(),
      });
      setRegistration(response);
      setVerificationCode('');
      setSuccess(t('auth.registrationStarted'));
    } catch (requestError) {
      setError(formatApiError(requestError, t('auth.registrationFailed')));
    } finally {
      setLoadingAction(null);
    }
  }

  async function handleConfirmRegistration(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!registration) return;
    setError(null);
    setSuccess(null);

    if (!/^\d{4,12}$/.test(verificationCode.trim())) {
      setError(t('auth.codeInvalid'));
      return;
    }

    setLoadingAction('confirm-registration');
    try {
      const response = await api.sellerAuth.confirmRegistration({
        registration_id: registration.registration_id,
        code: verificationCode.trim(),
      });
      setStoredToken(response.access_token, storageScope);
      onTokenSaved();
    } catch (requestError) {
      setError(formatApiError(requestError, t('auth.confirmFailed')));
    } finally {
      setLoadingAction(null);
    }
  }

  async function handleResendCode() {
    if (!registration) return;
    setError(null);
    setSuccess(null);
    setLoadingAction('resend-code');
    try {
      const response = await api.sellerAuth.resendCode({
        registration_id: registration.registration_id,
      });
      setRegistration({
        ...registration,
        expires_at: registration.expires_at,
      });
      setSuccess(t('auth.codeResent', { expiresAt: formatDateTime(response.verification_expires_at, language) }));
    } catch (requestError) {
      if (requestError instanceof ApiError && requestError.message.includes('not linked')) {
        setError(
          t('auth.botNotLinked', { command: registration.start_command }),
        );
      } else if (
        requestError instanceof ApiError &&
        requestError.message.includes('awaiting approval')
      ) {
        setError(t('auth.awaitingApproval'));
      } else {
        setError(formatApiError(requestError, t('auth.resendFailed')));
      }
    } finally {
      setLoadingAction(null);
    }
  }

  function validateLogin(): string | null {
    if (!EMAIL_RE.test(loginEmail.trim())) return t('auth.invalidEmail');
    if (!loginPassword) return t('auth.enterPassword');
    return null;
  }

  function validateRegistration(): string | null {
    if (!EMAIL_RE.test(registerEmail.trim())) return t('auth.invalidEmail');
    if (registerPassword.length < 8) return t('auth.passwordMin');
    if (!/[A-Za-z]/.test(registerPassword) || !/\d/.test(registerPassword)) {
      return t('auth.passwordComplexity');
    }
    if (registerPassword !== confirmPassword) return t('auth.passwordMismatch');
    if (!TELEGRAM_RE.test(telegramUsername.trim())) {
      return t('auth.invalidTelegram');
    }
    return null;
  }

  return (
    <main className="login-page seller-auth-page">
      <section className="login-card seller-auth-card">
        <p className="eyebrow">{t('app.brand')}</p>
        <h1>{t('auth.signInTitle')}</h1>
        <div className="tabs auth-tabs" role="tablist" aria-label="Seller auth">
          <button
            className={activeTab === 'login' ? 'tab-active' : ''}
            type="button"
            onClick={() => setActiveTab('login')}
          >
            {t('auth.loginTab')}
          </button>
          <button
            className={activeTab === 'register' ? 'tab-active' : ''}
            type="button"
            onClick={() => setActiveTab('register')}
          >
            {t('auth.registerTab')}
          </button>
        </div>

        {authError ? <div className="form-error">{authError}</div> : null}
        {error ? <div className="form-error">{error}</div> : null}
        {success ? <div className="success-banner">{success}</div> : null}

        {activeTab === 'login' ? (
          <form className="form-stack" onSubmit={handleLogin}>
            <label className="field">
              <span>{t('auth.email')}</span>
              <input
                autoComplete="email"
                inputMode="email"
                type="email"
                value={loginEmail}
                onChange={(event) => setLoginEmail(event.target.value)}
              />
            </label>
            <label className="field">
              <span>{t('auth.password')}</span>
              <input
                autoComplete="current-password"
                type="password"
                value={loginPassword}
                onChange={(event) => setLoginPassword(event.target.value)}
              />
            </label>
            <StorageScopeControls value={storageScope} onChange={setStorageScope} />
            <button
              className="button button-primary button-wide"
              disabled={loadingAction === 'login'}
              type="submit"
            >
              {loadingAction === 'login' ? t('auth.signingIn') : t('auth.signIn')}
            </button>
          </form>
        ) : (
          <div className="auth-registration-grid">
            <form className="form-stack" onSubmit={handleStartRegistration}>
              <label className="field">
                  <span>{t('auth.email')}</span>
                <input
                  autoComplete="email"
                  inputMode="email"
                  type="email"
                  value={registerEmail}
                  onChange={(event) => setRegisterEmail(event.target.value)}
                />
              </label>
              <label className="field">
                  <span>{t('auth.password')}</span>
                <input
                  autoComplete="new-password"
                  type="password"
                  value={registerPassword}
                  onChange={(event) => setRegisterPassword(event.target.value)}
                />
              </label>
              <label className="field">
                  <span>{t('auth.confirmPassword')}</span>
                <input
                  autoComplete="new-password"
                  type="password"
                  value={confirmPassword}
                  onChange={(event) => setConfirmPassword(event.target.value)}
                />
              </label>
              <label className="field">
                  <span>{t('auth.telegramUsername')}</span>
                <input
                  autoComplete="off"
                  placeholder="@sellername"
                  value={telegramUsername}
                  onChange={(event) => setTelegramUsername(event.target.value)}
                />
              </label>
              <StorageScopeControls value={storageScope} onChange={setStorageScope} />
              <button
                className="button button-primary button-wide"
                disabled={loadingAction === 'start-registration'}
                type="submit"
              >
                {loadingAction === 'start-registration' ? t('auth.starting') : t('auth.startRegistration')}
              </button>
            </form>

            {registration ? (
              <form className="telegram-confirm-panel" onSubmit={handleConfirmRegistration}>
                <div>
                  <span>{t('auth.botStartCommand')}</span>
                  <code>{registration.start_command}</code>
                </div>
                {registration.bot_start_link ? (
                  <a
                    className="button button-secondary"
                    href={registration.bot_start_link}
                    rel="noreferrer"
                    target="_blank"
                  >
                    {t('auth.openBot2')}
                  </a>
                ) : null}
                <p className="muted-text">
                  {t('auth.registrationHelp', {
                    expiresAt: formatDateTime(registration.expires_at, language),
                  })}
                </p>
                <label className="field">
                  <span>{t('auth.confirmationCode')}</span>
                  <input
                    inputMode="numeric"
                    value={verificationCode}
                    onChange={(event) => setVerificationCode(event.target.value)}
                  />
                </label>
                <div className="inline-actions">
                  <button
                    className="button button-primary"
                    disabled={loadingAction === 'confirm-registration'}
                    type="submit"
                  >
                    {loadingAction === 'confirm-registration' ? t('auth.confirming') : t('common.confirm')}
                  </button>
                  <button
                    className="button button-secondary"
                    disabled={loadingAction === 'resend-code'}
                    type="button"
                    onClick={handleResendCode}
                  >
                    {loadingAction === 'resend-code' ? t('auth.sending') : t('auth.resendCode')}
                  </button>
                </div>
              </form>
            ) : null}
          </div>
        )}

        {import.meta.env.DEV ? (
          <button className="text-button dev-token-link" type="button" onClick={() => setShowDevTokenLogin(true)}>
            {t('auth.devFallback')}
          </button>
        ) : null}
      </section>
    </main>
  );
}

function StorageScopeControls({
  value,
  onChange,
}: {
  value: TokenStorageScope;
  onChange: (scope: TokenStorageScope) => void;
}) {
  const { t } = useI18n();

  return (
    <fieldset className="segmented-field">
      <legend>{t('auth.storage')}</legend>
      <label>
        <input
          checked={value === 'session'}
          name="token-scope"
          type="radio"
          onChange={() => onChange('session')}
        />
        {t('auth.thisTab')}
      </label>
      <label>
        <input
          checked={value === 'local'}
          name="token-scope"
          type="radio"
          onChange={() => onChange('local')}
        />
        {t('auth.thisBrowser')}
      </label>
    </fieldset>
  );
}

function formatApiError(error: unknown, fallback: string): string {
  if (error instanceof ApiError || error instanceof Error) {
    return error.message;
  }
  return fallback;
}

function formatDateTime(value: string, language: 'ru' | 'en'): string {
  return new Intl.DateTimeFormat(languageToLocale(language), {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(new Date(value));
}
