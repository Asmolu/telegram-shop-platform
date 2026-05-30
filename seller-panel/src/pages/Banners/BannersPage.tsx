import { ChangeEvent, FormEvent, useEffect, useState } from 'react';
import { api, resolveMediaUrl } from '../../shared/api';
import type { Banner, BannerPayload, BannerTargetType } from '../../shared/api';
import { ErrorState, LoadingState } from '../../shared/ui/DataState';
import { StatusBadge } from '../../shared/ui/StatusBadge';
import { formatDate, fromDateTimeInput, toDateTimeInput } from '../../shared/utils/format';

interface PageProps {
  onAuthExpired: () => void;
}

interface BannerFormState {
  title: string;
  subtitle: string;
  imagePath: string;
  targetType: BannerTargetType;
  targetId: string;
  externalUrl: string;
  position: string;
  isActive: boolean;
  startsAt: string;
  endsAt: string;
}

const initialForm: BannerFormState = {
  title: '',
  subtitle: '',
  imagePath: '',
  targetType: 'product',
  targetId: '',
  externalUrl: '',
  position: '0',
  isActive: false,
  startsAt: '',
  endsAt: '',
};

export function BannersPage({ onAuthExpired }: PageProps) {
  const [banners, setBanners] = useState<Banner[]>([]);
  const [editingBanner, setEditingBanner] = useState<Banner | null>(null);
  const [form, setForm] = useState<BannerFormState>(initialForm);
  const [imageFile, setImageFile] = useState<File | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  function loadBanners() {
    setLoading(true);
    setError(null);
    api.banners
      .listAdmin({ limit: 100, offset: 0 })
      .then((bannerList) => setBanners(bannerList.items))
      .catch(setError)
      .finally(() => setLoading(false));
  }

  useEffect(() => {
    loadBanners();
  }, []);

  function selectBanner(banner: Banner) {
    setEditingBanner(banner);
    setForm({
      title: banner.title,
      subtitle: banner.subtitle ?? '',
      imagePath: banner.image_path,
      targetType: banner.target_type ?? 'product',
      targetId: banner.target_id ? String(banner.target_id) : '',
      externalUrl: banner.external_url ?? '',
      position: String(banner.position),
      isActive: banner.is_active,
      startsAt: toDateTimeInput(banner.starts_at),
      endsAt: toDateTimeInput(banner.ends_at),
    });
    setImageFile(null);
    setFormError(null);
  }

  function resetForm() {
    setEditingBanner(null);
    setForm(initialForm);
    setImageFile(null);
    setFormError(null);
  }

  function handleImageChange(event: ChangeEvent<HTMLInputElement>) {
    setImageFile(event.target.files?.[0] ?? null);
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSaving(true);
    setFormError(null);
    setNotice(null);

    try {
      let imagePath = form.imagePath.trim();
      if (imageFile) {
        const uploaded = await api.banners.uploadImage(imageFile, form.title);
        imagePath = uploaded.file_path;
      }

      if (!imagePath) {
        setFormError('Banner image is required.');
        return;
      }

      if (form.targetType !== 'external_url' && !form.targetId.trim()) {
        setFormError('Target ID is required for product, category, and promo banners.');
        return;
      }

      const payload: BannerPayload = {
        title: form.title.trim(),
        subtitle: form.subtitle.trim() || null,
        image_path: imagePath,
        target_type: form.targetType,
        target_id: form.targetType === 'external_url' ? null : Number(form.targetId),
        external_url: form.targetType === 'external_url' ? form.externalUrl.trim() || null : null,
        position: Number(form.position || 0),
        is_active: form.isActive,
        starts_at: fromDateTimeInput(form.startsAt),
        ends_at: fromDateTimeInput(form.endsAt),
      };

      if (editingBanner) {
        await api.banners.update(editingBanner.id, payload);
        setNotice('Banner updated.');
      } else {
        await api.banners.create(payload);
        setNotice('Banner created.');
      }

      resetForm();
      loadBanners();
    } catch (requestError) {
      setError(requestError);
    } finally {
      setSaving(false);
    }
  }

  async function toggleBanner(banner: Banner) {
    try {
      const updated = banner.is_active
        ? await api.banners.deactivate(banner.id)
        : await api.banners.activate(banner.id);
      setBanners((current) => current.map((item) => (item.id === updated.id ? updated : item)));
    } catch (requestError) {
      setError(requestError);
    }
  }

  if (loading) return <LoadingState title="Loading banners" />;
  if (error) {
    return <ErrorState error={error} onRetry={loadBanners} onAuthExpired={onAuthExpired} />;
  }

  return (
    <div className="split-view">
      <div className="page-stack">
        {notice ? <div className="success-banner">{notice}</div> : null}
        <div className="table-panel">
          <table>
            <thead>
              <tr>
                <th>Preview</th>
                <th>Title</th>
                <th>Target</th>
                <th>Position</th>
                <th>Status</th>
                <th>Dates</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {banners.length === 0 ? (
                <tr>
                  <td colSpan={7}>
                    <div className="empty-table">No banners have been created.</div>
                  </td>
                </tr>
              ) : (
                banners.map((banner) => (
                  <tr key={banner.id}>
                    <td>
                      <img
                        className="table-image banner-thumb"
                        src={resolveMediaUrl(banner.image_url)}
                        alt={banner.title}
                      />
                    </td>
                    <td>
                      <strong>{banner.title}</strong>
                      <small>{banner.subtitle ?? 'No subtitle'}</small>
                    </td>
                    <td>
                      <span>{banner.target_type ?? 'None'}</span>
                      <small>
                        {banner.target_type === 'external_url'
                          ? banner.external_url
                          : banner.target_id ?? 'No target'}
                      </small>
                    </td>
                    <td>{banner.position}</td>
                    <td>
                      <StatusBadge status={banner.is_active ? 'ACTIVE' : 'INACTIVE'} />
                    </td>
                    <td>
                      <small>{formatDate(banner.starts_at)}</small>
                      <small>{formatDate(banner.ends_at)}</small>
                    </td>
                    <td>
                      <div className="table-actions">
                        <button className="text-button" type="button" onClick={() => selectBanner(banner)}>
                          Edit
                        </button>
                        <button className="text-button" type="button" onClick={() => toggleBanner(banner)}>
                          {banner.is_active ? 'Deactivate' : 'Activate'}
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
          <h2>{editingBanner ? 'Edit banner' : 'Create banner'}</h2>
          {editingBanner ? (
            <button className="text-button" type="button" onClick={resetForm}>
              New
            </button>
          ) : null}
        </div>
        {formError ? <div className="form-error">{formError}</div> : null}
        <form className="form-stack" onSubmit={handleSubmit}>
          <label className="field">
            <span>Title</span>
            <input
              value={form.title}
              onChange={(event) => setForm((current) => ({ ...current, title: event.target.value }))}
            />
          </label>
          <label className="field">
            <span>Subtitle</span>
            <input
              value={form.subtitle}
              onChange={(event) =>
                setForm((current) => ({ ...current, subtitle: event.target.value }))
              }
            />
          </label>
          <label className="field">
            <span>Image file</span>
            <input accept="image/*" type="file" onChange={handleImageChange} />
          </label>
          <label className="field">
            <span>Image path</span>
            <input
              value={form.imagePath}
              onChange={(event) =>
                setForm((current) => ({ ...current, imagePath: event.target.value }))
              }
              placeholder="Filled after upload or paste existing path"
            />
          </label>
          <label className="field">
            <span>Target type</span>
            <select
              value={form.targetType}
              onChange={(event) =>
                setForm((current) => ({
                  ...current,
                  targetType: event.target.value as BannerTargetType,
                }))
              }
            >
              <option value="product">Product</option>
              <option value="category">Category</option>
              <option value="promo">Promo</option>
              <option value="external_url">External URL</option>
            </select>
          </label>
          <label className="field">
            <span>Target ID</span>
            <input
              type="number"
              value={form.targetId}
              onChange={(event) =>
                setForm((current) => ({ ...current, targetId: event.target.value }))
              }
            />
          </label>
          <label className="field">
            <span>External URL</span>
            <input
              value={form.externalUrl}
              onChange={(event) =>
                setForm((current) => ({ ...current, externalUrl: event.target.value }))
              }
            />
          </label>
          <label className="field">
            <span>Position</span>
            <input
              min="0"
              type="number"
              value={form.position}
              onChange={(event) =>
                setForm((current) => ({ ...current, position: event.target.value }))
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
          {form.title || form.subtitle ? (
            <div className="banner-preview">
              <strong>{form.title || 'Banner title'}</strong>
              <span>{form.subtitle || 'Optional subtitle'}</span>
            </div>
          ) : null}
          <button className="button button-primary" disabled={saving} type="submit">
            {saving ? 'Saving...' : editingBanner ? 'Save banner' : 'Create banner'}
          </button>
        </form>
      </aside>
    </div>
  );
}
