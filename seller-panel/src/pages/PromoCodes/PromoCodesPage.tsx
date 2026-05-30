import { FormEvent, useEffect, useState } from 'react';
import { api } from '../../shared/api';
import type { DiscountType, PromoCode, PromoCodePayload } from '../../shared/api';
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
        setNotice('Promo code updated.');
      } else {
        await api.promoCodes.create(buildPayload());
        setNotice('Promo code created.');
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
      setNotice(`${promoCode.code} deactivated.`);
      loadPromoCodes();
    } catch (requestError) {
      setError(requestError);
    }
  }

  if (loading) return <LoadingState title="Loading promo codes" />;
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
                <th>Code</th>
                <th>Discount</th>
                <th>Active</th>
                <th>Starts</th>
                <th>Ends</th>
                <th>Usage limit</th>
                <th>Used count</th>
                <th>Per user</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {promoCodes.length === 0 ? (
                <tr>
                  <td colSpan={9}>
                    <div className="empty-table">No promo codes have been created.</div>
                  </td>
                </tr>
              ) : (
                promoCodes.map((promoCode) => (
                  <tr key={promoCode.id}>
                    <td>
                      <strong>{promoCode.code}</strong>
                      <small>ID {promoCode.id}</small>
                    </td>
                    <td>
                      {promoCode.discount_type} {formatMoney(promoCode.discount_value)}
                    </td>
                    <td>
                      <StatusBadge status={promoCode.is_active ? 'ACTIVE' : 'INACTIVE'} />
                    </td>
                    <td>{formatDate(promoCode.starts_at)}</td>
                    <td>{formatDate(promoCode.ends_at)}</td>
                    <td>{promoCode.usage_limit ?? 'No limit'}</td>
                    <td>Not exposed</td>
                    <td>{promoCode.per_user_limit ?? 'No limit'}</td>
                    <td>
                      <div className="table-actions">
                        <button className="text-button" type="button" onClick={() => selectPromo(promoCode)}>
                          Edit
                        </button>
                        <button
                          className="text-button danger-text"
                          disabled={!promoCode.is_active}
                          type="button"
                          onClick={() => deactivatePromo(promoCode)}
                        >
                          Deactivate
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
          <h2>{editingPromo ? 'Edit promo code' : 'Create promo code'}</h2>
          {editingPromo ? (
            <button className="text-button" type="button" onClick={resetForm}>
              New
            </button>
          ) : null}
        </div>
        <form className="form-stack" onSubmit={handleSubmit}>
          <label className="field">
            <span>Code</span>
            <input
              value={form.code}
              onChange={(event) => setForm((current) => ({ ...current, code: event.target.value }))}
            />
          </label>
          <label className="field">
            <span>Discount type</span>
            <select
              value={form.discountType}
              onChange={(event) =>
                setForm((current) => ({
                  ...current,
                  discountType: event.target.value as DiscountType,
                }))
              }
            >
              <option value="PERCENT">Percent</option>
              <option value="FIXED">Fixed</option>
            </select>
          </label>
          <label className="field">
            <span>Discount value</span>
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
              <span>Starts at</span>
              <input
                type="datetime-local"
                value={form.startsAt}
                onChange={(event) =>
                  setForm((current) => ({ ...current, startsAt: event.target.value }))
                }
              />
            </label>
            <label className="field">
              <span>Ends at</span>
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
            <span>Usage limit</span>
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
            <span>Per-user limit</span>
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
            Active
          </label>
          <button className="button button-primary" disabled={saving} type="submit">
            {saving ? 'Saving...' : editingPromo ? 'Save promo code' : 'Create promo code'}
          </button>
        </form>
      </aside>
    </div>
  );
}
