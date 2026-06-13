import React from 'react';
import {
  getPersonalData,
  toApiErrorMessage,
  updatePersonalData,
  type PersonalDataUpdate,
} from '../shared/api';
import { useAuth } from '../shared/auth/AuthProvider';
import { getAuthPath, useRouter } from '../shared/router/RouterProvider';
import { EmptyState, InlineNotice, PageLoader, TopBar } from '../shared/ui';

type PersonalDataForm = {
  recipientName: string;
  contactPhone: string;
  city: string;
  heightCm: string;
  weightKg: string;
  telegramUsername: string;
  persistentComment: string;
};

const emptyForm: PersonalDataForm = {
  recipientName: '',
  contactPhone: '',
  city: '',
  heightCm: '',
  weightKg: '',
  telegramUsername: '',
  persistentComment: '',
};

export function PersonalDataPage() {
  const { currentPath, navigate } = useRouter();
  const { isAuthenticated, telegramUser } = useAuth();
  const [form, setForm] = React.useState<PersonalDataForm>(emptyForm);
  const [loading, setLoading] = React.useState(true);
  const [saving, setSaving] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [saved, setSaved] = React.useState(false);

  React.useEffect(() => {
    if (!isAuthenticated) {
      setLoading(false);
      return;
    }

    let cancelled = false;
    setLoading(true);
    setError(null);
    getPersonalData()
      .then((personalData) => {
        if (cancelled) return;
        setForm({
          recipientName: personalData.recipient_name ?? '',
          contactPhone: personalData.contact_phone ?? '',
          city: personalData.city ?? '',
          heightCm: personalData.height_cm == null ? '' : String(personalData.height_cm),
          weightKg: personalData.weight_kg == null ? '' : String(personalData.weight_kg),
          telegramUsername: personalData.telegram_username ?? telegramUser?.username ?? '',
          persistentComment: personalData.persistent_comment ?? '',
        });
      })
      .catch((loadError) => {
        if (!cancelled) setError(toApiErrorMessage(loadError));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [isAuthenticated, telegramUser?.username]);

  function updateField(field: keyof PersonalDataForm, value: string) {
    setSaved(false);
    setError(null);
    setForm((current) => ({ ...current, [field]: value }));
  }

  async function save(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSaved(false);
    setError(null);

    const heightCm = parseOptionalPositiveNumber(form.heightCm);
    const weightKg = parseOptionalPositiveNumber(form.weightKg);
    if (heightCm === false || (heightCm !== null && !Number.isInteger(heightCm))) {
      setError('Рост должен быть положительным целым числом.');
      return;
    }
    if (weightKg === false) {
      setError('Вес должен быть положительным числом.');
      return;
    }
    if (form.contactPhone.trim() && !/\d/.test(form.contactPhone)) {
      setError('Контактный телефон должен содержать хотя бы одну цифру.');
      return;
    }

    const payload: PersonalDataUpdate = {
      recipient_name: optionalText(form.recipientName),
      contact_phone: optionalText(form.contactPhone),
      city: optionalText(form.city),
      height_cm: heightCm,
      weight_kg: weightKg,
      telegram_username: optionalText(form.telegramUsername),
      persistent_comment: optionalText(form.persistentComment),
    };

    setSaving(true);
    try {
      const personalData = await updatePersonalData(payload);
      setForm({
        recipientName: personalData.recipient_name ?? '',
        contactPhone: personalData.contact_phone ?? '',
        city: personalData.city ?? '',
        heightCm: personalData.height_cm == null ? '' : String(personalData.height_cm),
        weightKg: personalData.weight_kg == null ? '' : String(personalData.weight_kg),
        telegramUsername: personalData.telegram_username ?? '',
        persistentComment: personalData.persistent_comment ?? '',
      });
      setSaved(true);
    } catch (saveError) {
      setError(toApiErrorMessage(saveError));
    } finally {
      setSaving(false);
    }
  }

  if (!isAuthenticated) {
    return (
      <div className="page page--gradient-header">
        <TopBar title="Личные данные" variant="marketplace" onBack={() => navigate('/profile')} />
        <EmptyState
          title="Нужен вход через Telegram"
          message="Сохранение личных данных доступно после входа."
          actionLabel="Войти"
          onAction={() => navigate(getAuthPath(currentPath))}
        />
      </div>
    );
  }

  return (
    <div className="page page--gradient-header">
      <TopBar title="Личные данные" variant="marketplace" onBack={() => navigate('/profile')} />
      {loading ? <PageLoader text="Загружаем личные данные..." /> : null}
      {!loading ? (
        <section className="detail-card personal-data-card">
          <p className="muted-text">Эти данные будут автоматически подставляться при оформлении заказа.</p>
          {saved ? <InlineNotice tone="success">Личные данные сохранены.</InlineNotice> : null}
          {error ? <InlineNotice tone="danger">{error}</InlineNotice> : null}
          <form className="checkout-form personal-data-form" onSubmit={save}>
            <label>
              Имя получателя
              <input value={form.recipientName} maxLength={255} onChange={(event) => updateField('recipientName', event.target.value)} />
            </label>
            <label>
              Контактный телефон
              <input value={form.contactPhone} maxLength={32} inputMode="tel" onChange={(event) => updateField('contactPhone', event.target.value)} />
            </label>
            <label>
              Город
              <input value={form.city} maxLength={255} onChange={(event) => updateField('city', event.target.value)} />
            </label>
            <div className="two-inputs">
              <label>
                Рост
                <input value={form.heightCm} inputMode="numeric" placeholder="см" onChange={(event) => updateField('heightCm', event.target.value)} />
              </label>
              <label>
                Вес
                <input value={form.weightKg} inputMode="decimal" placeholder="кг" onChange={(event) => updateField('weightKg', event.target.value)} />
              </label>
            </div>
            <label>
              Telegram тег
              <input value={form.telegramUsername} maxLength={33} placeholder="@username" autoCapitalize="none" onChange={(event) => updateField('telegramUsername', event.target.value)} />
            </label>
            <label>
              Постоянный комментарий
              <textarea value={form.persistentComment} maxLength={500} rows={4} onChange={(event) => updateField('persistentComment', event.target.value)} />
            </label>
            <button className="primary-button full-width" type="submit" disabled={saving}>
              {saving ? 'Сохраняем...' : 'Сохранить'}
            </button>
          </form>
        </section>
      ) : null}
    </div>
  );
}

function optionalText(value: string) {
  return value.trim() || null;
}

function parseOptionalPositiveNumber(value: string): number | null | false {
  if (!value.trim()) return null;
  const parsed = Number(value.replace(',', '.'));
  return Number.isFinite(parsed) && parsed > 0 ? parsed : false;
}
