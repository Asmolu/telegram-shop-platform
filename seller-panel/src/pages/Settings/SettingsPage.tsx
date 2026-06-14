import { FormEvent, useEffect, useState } from 'react';
import { API_BASE_URL, ApiError, api } from '../../shared/api';
import { clearStoredToken, getTokenStorageScope } from '../../shared/auth/tokenStorage';
import { useI18n } from '../../shared/i18n';

interface PageProps {
  onAuthExpired: () => void;
}

export function SettingsPage({ onAuthExpired }: PageProps) {
  const { t } = useI18n();
  const tokenScope = getTokenStorageScope();
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [form, setForm] = useState({
    enabled: false,
    phone: '',
    bankName: '',
    recipientName: '',
  });

  useEffect(() => {
    api.paymentSettings
      .get()
      .then((settings) => {
        setForm({
          enabled: settings.is_manual_sbp_enabled,
          phone: settings.seller_phone_display ?? '',
          bankName: settings.seller_bank_name ?? '',
          recipientName: settings.seller_recipient_name ?? '',
        });
      })
      .catch(handleError)
      .finally(() => setLoading(false));
  }, []);

  function handleError(requestError: unknown) {
    if (requestError instanceof ApiError && [401, 403].includes(requestError.status)) {
      onAuthExpired();
      return;
    }
    setError(requestError instanceof Error ? requestError.message : 'Не удалось выполнить запрос.');
  }

  async function savePaymentSettings(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSaving(true);
    setError(null);
    setNotice(null);
    try {
      const settings = await api.paymentSettings.update({
        is_manual_sbp_enabled: form.enabled,
        seller_phone: form.phone.trim() || null,
        seller_bank_name: form.bankName.trim() || null,
        seller_recipient_name: form.recipientName.trim() || null,
      });
      setForm((current) => ({
        ...current,
        phone: settings.seller_phone_display ?? current.phone,
      }));
      setNotice('Настройки ручной оплаты сохранены.');
    } catch (requestError) {
      handleError(requestError);
    } finally {
      setSaving(false);
    }
  }

  function clearToken() {
    clearStoredToken();
    onAuthExpired();
  }

  return (
    <div className="page-stack">
      <section className="panel payment-settings-panel">
        <div className="section-heading">
          <div>
            <h2>Ручная оплата через СБП</h2>
            <p>
              Клиенты переводят 100% суммы напрямую продавцу по номеру телефона.
              Платформа не подтверждает оплату автоматически: перевод проверяет продавец.
            </p>
          </div>
          <span className={`payment-setting-state ${form.enabled ? 'is-enabled' : ''}`}>
            {form.enabled ? 'Включено' : 'Выключено'}
          </span>
        </div>

        {error ? <div className="error-banner">{error}</div> : null}
        {notice ? <div className="success-banner">{notice}</div> : null}

        <form className="payment-settings-form" onSubmit={savePaymentSettings}>
          <label className="toggle-field payment-settings-toggle">
            <input
              checked={form.enabled}
              disabled={loading || saving}
              type="checkbox"
              onChange={(event) =>
                setForm((current) => ({ ...current, enabled: event.target.checked }))
              }
            />
            <span>
              <strong>Включить ручную оплату через СБП</strong>
              <small>Новые заказы будут резервировать товар на 30 минут.</small>
            </span>
          </label>

          <div className="form-grid two-columns">
            <label>
              <span>Телефон продавца</span>
              <input
                disabled={loading || saving}
                inputMode="tel"
                placeholder="+7 (999) 999-99-99"
                value={form.phone}
                onChange={(event) =>
                  setForm((current) => ({
                    ...current,
                    phone: formatRussianPhoneInput(event.target.value),
                  }))
                }
              />
              <small>Обязательно для включения оплаты.</small>
            </label>
            <label>
              <span>Банк</span>
              <input
                disabled={loading || saving}
                maxLength={100}
                placeholder="Например, Сбербанк"
                value={form.bankName}
                onChange={(event) =>
                  setForm((current) => ({ ...current, bankName: event.target.value }))
                }
              />
            </label>
            <label>
              <span>Имя получателя</span>
              <input
                disabled={loading || saving}
                maxLength={100}
                placeholder="Например, Иван И."
                value={form.recipientName}
                onChange={(event) =>
                  setForm((current) => ({ ...current, recipientName: event.target.value }))
                }
              />
            </label>
          </div>

          <button className="button button-primary" disabled={loading || saving} type="submit">
            {saving ? 'Сохраняем...' : 'Сохранить настройки оплаты'}
          </button>
        </form>
      </section>

      <section className="panel">
        <h2>{t('settings.api')}</h2>
        <dl className="settings-list">
          <div>
            <dt>{t('settings.baseUrl')}</dt>
            <dd><code>{API_BASE_URL}</code></dd>
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

function formatRussianPhoneInput(value: string) {
  const rawDigits = value.replace(/\D/g, '');
  const national = (rawDigits.startsWith('7') || rawDigits.startsWith('8')
    ? rawDigits.slice(1)
    : rawDigits
  ).slice(0, 10);
  if (!national) return '';

  let result = `+7 (${national.slice(0, 3)}`;
  if (national.length >= 3) result += ')';
  if (national.length > 3) result += ` ${national.slice(3, 6)}`;
  if (national.length > 6) result += `-${national.slice(6, 8)}`;
  if (national.length > 8) result += `-${national.slice(8, 10)}`;
  return result;
}
