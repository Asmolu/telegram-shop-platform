import { FormEvent, useState } from 'react';
import { ApiError, api } from '../../shared/api';
import type { SellerRegistrationStartResponse } from '../../shared/api';
import { setStoredToken, type TokenStorageScope } from '../../shared/auth/tokenStorage';
import { DevTokenLoginPage } from './DevTokenLoginPage';

interface SellerAuthPageProps {
  authError: string | null;
  onTokenSaved: () => void;
}

type AuthTab = 'login' | 'register';

const EMAIL_RE = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;
const TELEGRAM_RE = /^@?[A-Za-z0-9_]{5,32}$/;

export function SellerAuthPage({ authError, onTokenSaved }: SellerAuthPageProps) {
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
      setError(formatApiError(requestError, 'Could not sign in.'));
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
      setSuccess(
        'Registration started. Open Bot 2, send the start command, and enter the code it sends.',
      );
    } catch (requestError) {
      setError(formatApiError(requestError, 'Could not start registration.'));
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
      setError('Enter the numeric verification code from Telegram.');
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
      setError(formatApiError(requestError, 'Could not confirm registration.'));
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
      setSuccess(`Code resent. It expires at ${formatDateTime(response.verification_expires_at)}.`);
    } catch (requestError) {
      if (requestError instanceof ApiError && requestError.message.includes('not linked')) {
        setError(
          `Open Bot 2 and send ${registration.start_command} first. Then use resend if the code does not arrive.`,
        );
      } else {
        setError(formatApiError(requestError, 'Could not resend the code.'));
      }
    } finally {
      setLoadingAction(null);
    }
  }

  function validateLogin(): string | null {
    if (!EMAIL_RE.test(loginEmail.trim())) return 'Enter a valid email address.';
    if (!loginPassword) return 'Enter your password.';
    return null;
  }

  function validateRegistration(): string | null {
    if (!EMAIL_RE.test(registerEmail.trim())) return 'Enter a valid email address.';
    if (registerPassword.length < 8) return 'Password must be at least 8 characters.';
    if (!/[A-Za-z]/.test(registerPassword) || !/\d/.test(registerPassword)) {
      return 'Password must contain at least one letter and one digit.';
    }
    if (registerPassword !== confirmPassword) return 'Passwords do not match.';
    if (!TELEGRAM_RE.test(telegramUsername.trim())) {
      return 'Enter a Telegram username like @sellername.';
    }
    return null;
  }

  return (
    <main className="login-page seller-auth-page">
      <section className="login-card seller-auth-card">
        <p className="eyebrow">Seller Portal</p>
        <h1>Sign in</h1>
        <div className="tabs auth-tabs" role="tablist" aria-label="Seller auth">
          <button
            className={activeTab === 'login' ? 'tab-active' : ''}
            type="button"
            onClick={() => setActiveTab('login')}
          >
            Login
          </button>
          <button
            className={activeTab === 'register' ? 'tab-active' : ''}
            type="button"
            onClick={() => setActiveTab('register')}
          >
            Registration
          </button>
        </div>

        {authError ? <div className="form-error">{authError}</div> : null}
        {error ? <div className="form-error">{error}</div> : null}
        {success ? <div className="success-banner">{success}</div> : null}

        {activeTab === 'login' ? (
          <form className="form-stack" onSubmit={handleLogin}>
            <label className="field">
              <span>Email</span>
              <input
                autoComplete="email"
                inputMode="email"
                type="email"
                value={loginEmail}
                onChange={(event) => setLoginEmail(event.target.value)}
              />
            </label>
            <label className="field">
              <span>Password</span>
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
              {loadingAction === 'login' ? 'Signing in...' : 'Sign in'}
            </button>
          </form>
        ) : (
          <div className="auth-registration-grid">
            <form className="form-stack" onSubmit={handleStartRegistration}>
              <label className="field">
                <span>Email</span>
                <input
                  autoComplete="email"
                  inputMode="email"
                  type="email"
                  value={registerEmail}
                  onChange={(event) => setRegisterEmail(event.target.value)}
                />
              </label>
              <label className="field">
                <span>Password</span>
                <input
                  autoComplete="new-password"
                  type="password"
                  value={registerPassword}
                  onChange={(event) => setRegisterPassword(event.target.value)}
                />
              </label>
              <label className="field">
                <span>Confirm password</span>
                <input
                  autoComplete="new-password"
                  type="password"
                  value={confirmPassword}
                  onChange={(event) => setConfirmPassword(event.target.value)}
                />
              </label>
              <label className="field">
                <span>Telegram username</span>
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
                {loadingAction === 'start-registration' ? 'Starting...' : 'Start registration'}
              </button>
            </form>

            {registration ? (
              <form className="telegram-confirm-panel" onSubmit={handleConfirmRegistration}>
                <div>
                  <span>Bot 2 start command</span>
                  <code>{registration.start_command}</code>
                </div>
                {registration.bot_start_link ? (
                  <a
                    className="button button-secondary"
                    href={registration.bot_start_link}
                    rel="noreferrer"
                    target="_blank"
                  >
                    Open Bot 2
                  </a>
                ) : null}
                <p className="muted-text">
                  Send this command to Bot 2. The bot will reply with a verification code.
                  Registration expires at {formatDateTime(registration.expires_at)}.
                </p>
                <label className="field">
                  <span>Confirmation code</span>
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
                    {loadingAction === 'confirm-registration' ? 'Confirming...' : 'Confirm'}
                  </button>
                  <button
                    className="button button-secondary"
                    disabled={loadingAction === 'resend-code'}
                    type="button"
                    onClick={handleResendCode}
                  >
                    {loadingAction === 'resend-code' ? 'Sending...' : 'Resend code'}
                  </button>
                </div>
              </form>
            ) : null}
          </div>
        )}

        {import.meta.env.DEV ? (
          <button className="text-button dev-token-link" type="button" onClick={() => setShowDevTokenLogin(true)}>
            Use development JWT fallback
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
  return (
    <fieldset className="segmented-field">
      <legend>Storage</legend>
      <label>
        <input
          checked={value === 'session'}
          name="token-scope"
          type="radio"
          onChange={() => onChange('session')}
        />
        This tab
      </label>
      <label>
        <input
          checked={value === 'local'}
          name="token-scope"
          type="radio"
          onChange={() => onChange('local')}
        />
        This browser
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

function formatDateTime(value: string): string {
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(new Date(value));
}
