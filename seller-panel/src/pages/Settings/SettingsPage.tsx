import { ChangeEvent, FormEvent, useEffect, useState } from 'react';
import { API_BASE_URL, ApiError, api, resolveMediaUrl } from '../../shared/api';
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
  const [bannerSaving, setBannerSaving] = useState(false);
  const [bannerDeleting, setBannerDeleting] = useState(false);
  const [bannerUploading, setBannerUploading] = useState(false);
  const [contactsSaving, setContactsSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [form, setForm] = useState({
    enabled: false,
    phone: '',
    bankName: '',
    recipientName: '',
  });
  const [bannerForm, setBannerForm] = useState({
    enabled: false,
    imagePath: '',
    imageUrl: '',
  });
  const [contactsForm, setContactsForm] = useState({
    telegramUrl: '',
    whatsappUrl: '',
    instagramUrl: '',
  });

  useEffect(() => {
    Promise.all([
      api.paymentSettings.get(),
      api.paymentSuccessBanner.get(),
      api.sellerContacts.get(),
    ])
      .then(([settings, bannerSettings, contactSettings]) => {
        setForm({
          enabled: settings.is_manual_sbp_enabled,
          phone: settings.seller_phone_display ?? '',
          bankName: settings.seller_bank_name ?? '',
          recipientName: settings.seller_recipient_name ?? '',
        });
        setBannerForm({
          enabled: bannerSettings.enabled,
          imagePath: bannerSettings.image_path ?? '',
          imageUrl: bannerSettings.image_url ?? '',
        });
        setContactsForm({
          telegramUrl: contactSettings.telegram_url ?? '',
          whatsappUrl: contactSettings.whatsapp_url ?? '',
          instagramUrl: contactSettings.instagram_url ?? '',
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

  async function uploadPaymentSuccessBanner(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = '';
    if (!file) {
      return;
    }
    setError(null);
    setNotice(null);
    if (!file.type.startsWith('image/')) {
      setError('Загрузите изображение в формате JPG, PNG или WebP.');
      return;
    }

    setBannerUploading(true);
    try {
      const uploaded = await api.banners.uploadImage(file, undefined, 'vertical_banner');
      setBannerForm((current) => ({
        ...current,
        imagePath: uploaded.file_path,
        imageUrl: uploaded.url,
      }));
      setNotice('Баннер загружен. Сохраните настройки, чтобы применить его.');
    } catch (requestError) {
      handleError(requestError);
    } finally {
      setBannerUploading(false);
    }
  }

  async function savePaymentSuccessBannerSettings(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setNotice(null);
    if (bannerForm.enabled && !bannerForm.imagePath) {
      setError('Загрузите изображение перед включением баннера.');
      return;
    }

    setBannerSaving(true);
    try {
      const settings = await api.paymentSuccessBanner.update({
        enabled: bannerForm.enabled,
        image_path: bannerForm.imagePath || null,
      });
      setBannerForm({
        enabled: settings.enabled,
        imagePath: settings.image_path ?? '',
        imageUrl: settings.image_url ?? '',
      });
      setNotice('Настройки баннера после оплаты сохранены.');
    } catch (requestError) {
      handleError(requestError);
    } finally {
      setBannerSaving(false);
    }
  }

  async function deletePaymentSuccessBanner() {
    setError(null);
    setNotice(null);
    setBannerDeleting(true);
    try {
      const settings = await api.paymentSuccessBanner.delete();
      setBannerForm({
        enabled: settings.enabled,
        imagePath: settings.image_path ?? '',
        imageUrl: settings.image_url ?? '',
      });
      setNotice('Баннер после оплаты удален.');
    } catch (requestError) {
      handleError(requestError);
    } finally {
      setBannerDeleting(false);
    }
  }

  async function saveSellerContacts(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setNotice(null);
    setContactsSaving(true);
    try {
      const settings = await api.sellerContacts.update({
        telegram_url: contactsForm.telegramUrl.trim() || null,
        whatsapp_url: contactsForm.whatsappUrl.trim() || null,
        instagram_url: contactsForm.instagramUrl.trim() || null,
      });
      setContactsForm({
        telegramUrl: settings.telegram_url ?? '',
        whatsappUrl: settings.whatsapp_url ?? '',
        instagramUrl: settings.instagram_url ?? '',
      });
      setNotice('Контакты продавца сохранены.');
    } catch (requestError) {
      handleError(requestError);
    } finally {
      setContactsSaving(false);
    }
  }

  function clearToken() {
    clearStoredToken();
    onAuthExpired();
  }

  const bannerPreviewUrl = resolveMediaUrl(bannerForm.imageUrl || bannerForm.imagePath);
  const bannerBusy = loading || bannerSaving || bannerDeleting || bannerUploading;

  return (
    <div className="page-stack">
      {error ? <div className="error-banner">{error}</div> : null}
      {notice ? <div className="success-banner">{notice}</div> : null}

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

      <section className="panel paid-banner-settings-panel">
        <div className="section-heading">
          <div>
            <h2>Баннер после подтверждения оплаты</h2>
            <p>
              Показывается покупателю в Mini App один раз после подтверждения оплаты продавцом.
            </p>
          </div>
          <span className={`payment-setting-state ${bannerForm.enabled ? 'is-enabled' : ''}`}>
            {bannerForm.enabled ? 'Включено' : 'Выключено'}
          </span>
        </div>

        <form className="payment-settings-form" onSubmit={savePaymentSuccessBannerSettings}>
          <label className="toggle-field payment-settings-toggle">
            <input
              checked={bannerForm.enabled}
              disabled={bannerBusy}
              type="checkbox"
              onChange={(event) =>
                setBannerForm((current) => ({ ...current, enabled: event.target.checked }))
              }
            />
            <span>
              <strong>Показывать баннер после оплаты</strong>
              <small>Появится только для подтвержденных продавцом заказов.</small>
            </span>
          </label>

          <div className="paid-banner-settings-grid">
            <div className="paid-banner-preview">
              {bannerPreviewUrl ? (
                <img
                  alt="Баннер после подтверждения оплаты"
                  className="paid-banner-preview__media"
                  src={bannerPreviewUrl}
                />
              ) : (
                <span className="paid-banner-preview__empty">9:16</span>
              )}
            </div>

            <div className="paid-banner-controls">
              <label>
                <span>Изображение</span>
                <input
                  accept="image/*"
                  disabled={bannerBusy}
                  type="file"
                  onChange={uploadPaymentSuccessBanner}
                />
                <small>Вертикальный формат 9:16. Используются общие лимиты загрузок.</small>
              </label>

              {bannerForm.imagePath ? (
                <p className="paid-banner-path">{bannerForm.imagePath}</p>
              ) : null}

              <div className="settings-action-row">
                <button
                  className="button button-primary"
                  disabled={bannerBusy}
                  type="submit"
                >
                  {bannerSaving ? 'Сохраняем...' : 'Сохранить баннер'}
                </button>
                <button
                  className="button button-secondary"
                  disabled={bannerBusy || !bannerForm.imagePath}
                  type="button"
                  onClick={deletePaymentSuccessBanner}
                >
                  {bannerDeleting ? 'Удаляем...' : 'Удалить'}
                </button>
              </div>
              {bannerUploading ? <p className="paid-banner-path">Загружаем изображение...</p> : null}
            </div>
          </div>
        </form>
      </section>

      <section className="panel seller-contact-settings-panel">
        <div className="section-heading">
          <div>
            <h2>Контакты продавца</h2>
            <p>Ссылки отображаются в FAQ и в баннере после подтверждения оплаты.</p>
          </div>
        </div>

        <form className="payment-settings-form" onSubmit={saveSellerContacts}>
          <div className="form-grid">
            <label>
              <span>Telegram URL</span>
              <input
                disabled={loading || contactsSaving}
                inputMode="url"
                placeholder="https://t.me/username"
                value={contactsForm.telegramUrl}
                onChange={(event) =>
                  setContactsForm((current) => ({ ...current, telegramUrl: event.target.value }))
                }
              />
            </label>
            <label>
              <span>WhatsApp URL</span>
              <input
                disabled={loading || contactsSaving}
                inputMode="url"
                placeholder="https://wa.me/79999999999"
                value={contactsForm.whatsappUrl}
                onChange={(event) =>
                  setContactsForm((current) => ({ ...current, whatsappUrl: event.target.value }))
                }
              />
            </label>
            <label>
              <span>Instagram URL</span>
              <input
                disabled={loading || contactsSaving}
                inputMode="url"
                placeholder="https://instagram.com/username"
                value={contactsForm.instagramUrl}
                onChange={(event) =>
                  setContactsForm((current) => ({ ...current, instagramUrl: event.target.value }))
                }
              />
            </label>
          </div>

          <button className="button button-primary" disabled={loading || contactsSaving} type="submit">
            {contactsSaving ? 'Сохраняем...' : 'Сохранить контакты'}
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
