import { FormEvent, useEffect, useState } from 'react';
import { api } from '../../shared/api';
import type { DiscountType, PromoCode, PromoCodePayload } from '../../shared/api';
import { labelForEnum, useI18n } from '../../shared/i18n';
import { ErrorState, LoadingState } from '../../shared/ui/DataState';
import { StatusBadge } from '../../shared/ui/StatusBadge';
import { formatDate, formatMoney, fromDateTimeInput, toDateTimeInput } from '../../shared/utils/format';

interface PageProps {
  onAuthExpired: () => void;
}

interface PromoFormState {
  code: string;
  discountType: DiscountType;
  discountValue: string;
  isActive: boolean;
  startsAt: string;
  endsAt: string;
  usageLimit: string;
  perUserLimit: string;
}

const initialForm: PromoFormState = {
  code: '',
  discountType: 'PERCENT',
  discountValue: '',
  isActive: true,
  startsAt: '',
  endsAt: '',
  usageLimit: '',
  perUserLimit: '',
};

export function PromoCodesPage({ onAuthExpired }: PageProps) {
  const { language, t } = useI18n();
  const [promoCodes, setPromoCodes] = useState<PromoCode[]>([]);
  const [editingPromo, setEditingPromo] = useState<PromoCode | null>(null);
  const [form, setForm] = useState<PromoFormState>(initialForm);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [notice, setNotice] = useState<string | null>(null);

  function loadPromoCodes() {
    setLoading(true);
    setError(null);
    api.promoCodes
      .list({ limit: 100, offset: 0 })
      .then((promoList) => setPromoCodes(promoList.items))
      .catch(setError)
      .finally(() => setLoading(false));
  }

  useEffect(() => {
    loadPromoCodes();
  }, []);

  function selectPromo(promoCode: PromoCode) {
    setEditingPromo(promoCode);
    setForm({
      code: promoCode.code,
      discountType: promoCode.discount_type,
      discountValue: String(promoCode.discount_value),
      isActive: promoCode.is_active,
      startsAt: toDateTimeInput(promoCode.starts_at),
      endsAt: toDateTimeInput(promoCode.ends_at),
      usageLimit: promoCode.usage_limit ? String(promoCode.usage_limit) : '',
      perUserLimit: promoCode.per_user_limit ? String(promoCode.per_user_limit) : '',
    });
  }

  function resetForm() {
    setEditingPromo(null);
    setForm(initialForm);
  }

  function buildPayload(): PromoCodePayload {
    return {
      code: form.code.trim().toUpperCase(),
      discount_type: form.discountType,
      discount_value: form.discountValue,
      is_active: form.isActive,
      starts_at: fromDateTimeInput(form.startsAt),
      ends_at: fromDateTimeInput(form.endsAt),
      usage_limit: form.usageLimit ? Number(form.usageLimit) : null,
      per_user_limit: form.perUserLimit ? Number(form.perUserLimit) : null,
    };
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSaving(true);
    setNotice(null);

    try {
      if (editingPromo) {
        await api.promoCodes.update(editingPromo.id, buildPayload());
        setNotice(t('promo.updated'));
      } else {
        await api.promoCodes.create(buildPayload());
        setNotice(t('promo.created'));
      }
      resetForm();
      loadPromoCodes();
    } catch (requestError) {
      setError(requestError);
    } finally {
      setSaving(false);
    }
  }

  async function deactivatePromo(promoCode: PromoCode) {
    setNotice(null);
    try {
      await api.promoCodes.deactivate(promoCode.id);
      setNotice(t('promo.deactivated', { code: promoCode.code }));
      loadPromoCodes();
    } catch (requestError) {
      setError(requestError);
    }
  }

  if (loading) return <LoadingState title={t('promo.loading')} />;
  if (error) {
    return <ErrorState error={error} onRetry={loadPromoCodes} onAuthExpired={onAuthExpired} />;
  }

  return (
    <div className="split-view">
      <div className="page-stack">
        {notice ? <div className="success-banner">{notice}</div> : null}
        <div className="table-panel">
          <table>
            <thead>
              <tr>
                <th>{t('common.code')}</th>
                <th>{t('promo.discount')}</th>
                <th>{t('common.active')}</th>
                <th>{t('promo.starts')}</th>
                <th>{t('promo.ends')}</th>
                <th>{t('promo.usageLimit')}</th>
                <th>{t('promo.usedCount')}</th>
                <th>{t('promo.perUser')}</th>
                <th>{t('common.actions')}</th>
              </tr>
            </thead>
            <tbody>
              {promoCodes.length === 0 ? (
                <tr>
                  <td colSpan={9}>
                    <div className="empty-table">{t('promo.empty')}</div>
                  </td>
                </tr>
              ) : (
                promoCodes.map((promoCode) => (
                  <tr key={promoCode.id}>
                    <td>
                      <strong>{promoCode.code}</strong>
                      <small>{t('common.id')} {promoCode.id}</small>
                    </td>
                    <td>
                      {labelForEnum(promoCode.discount_type, t)} {formatMoney(promoCode.discount_value, language)}
                    </td>
                    <td>
                      <StatusBadge status={promoCode.is_active ? 'ACTIVE' : 'INACTIVE'} />
                    </td>
                    <td>{formatDate(promoCode.starts_at, language)}</td>
                    <td>{formatDate(promoCode.ends_at, language)}</td>
                    <td>{promoCode.usage_limit ?? t('common.noLimit')}</td>
                    <td>{t('common.notExposed')}</td>
                    <td>{promoCode.per_user_limit ?? t('common.noLimit')}</td>
                    <td>
                      <div className="table-actions">
                        <button className="text-button" type="button" onClick={() => selectPromo(promoCode)}>
                          {t('common.edit')}
                        </button>
                        <button
                          className="text-button danger-text"
                          disabled={!promoCode.is_active}
                          type="button"
                          onClick={() => deactivatePromo(promoCode)}
                        >
                          {t('common.deactivate')}
                        </button>
                      </div>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      <aside className="editor-panel">
        <div className="section-heading">
          <h2>{editingPromo ? t('promo.edit') : t('promo.create')}</h2>
          {editingPromo ? (
            <button className="text-button" type="button" onClick={resetForm}>
              {t('common.new')}
            </button>
          ) : null}
        </div>
        <form className="form-stack" onSubmit={handleSubmit}>
          <label className="field">
            <span>{t('common.code')}</span>
            <input
              value={form.code}
              onChange={(event) => setForm((current) => ({ ...current, code: event.target.value }))}
            />
          </label>
          <label className="field">
            <span>{t('promo.discountType')}</span>
            <select
              value={form.discountType}
              onChange={(event) =>
                setForm((current) => ({
                  ...current,
                  discountType: event.target.value as DiscountType,
                }))
              }
            >
              <option value="PERCENT">{labelForEnum('PERCENT', t)}</option>
              <option value="FIXED">{labelForEnum('FIXED', t)}</option>
            </select>
          </label>
          <label className="field">
            <span>{t('promo.discountValue')}</span>
            <input
              min="0"
              step="0.01"
              type="number"
              value={form.discountValue}
              onChange={(event) =>
                setForm((current) => ({ ...current, discountValue: event.target.value }))
              }
            />
          </label>
          <div className="date-grid">
            <label className="field">
              <span>{t('banners.startsAt')}</span>
              <input
                type="datetime-local"
                value={form.startsAt}
                onChange={(event) =>
                  setForm((current) => ({ ...current, startsAt: event.target.value }))
                }
              />
            </label>
            <label className="field">
              <span>{t('banners.endsAt')}</span>
              <input
                type="datetime-local"
                value={form.endsAt}
                onChange={(event) =>
                  setForm((current) => ({ ...current, endsAt: event.target.value }))
                }
              />
            </label>
          </div>
          <label className="field">
            <span>{t('promo.usageLimit')}</span>
            <input
              min="1"
              type="number"
              value={form.usageLimit}
              onChange={(event) =>
                setForm((current) => ({ ...current, usageLimit: event.target.value }))
              }
            />
          </label>
          <label className="field">
            <span>{t('promo.perUser')}</span>
            <input
              min="1"
              type="number"
              value={form.perUserLimit}
              onChange={(event) =>
                setForm((current) => ({ ...current, perUserLimit: event.target.value }))
              }
            />
          </label>
          <label className="toggle-label">
            <input
              checked={form.isActive}
              type="checkbox"
              onChange={(event) =>
                setForm((current) => ({ ...current, isActive: event.target.checked }))
              }
            />
            {t('common.active')}
          </label>
          <button className="button button-primary" disabled={saving} type="submit">
            {saving ? t('common.saving') : editingPromo ? t('promo.save') : t('promo.create')}
          </button>
        </form>
      </aside>
    </div>
  );
}
