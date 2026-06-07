import { ChangeEvent, FormEvent, useEffect, useState } from 'react';
import { api, resolveMediaUrl } from '../../shared/api';
import type {
  Banner,
  BannerDisplayType,
  BannerImageKind,
  BannerPayload,
  BannerTargetType,
} from '../../shared/api';
import { labelForEnum, useI18n } from '../../shared/i18n';
import { ErrorState, LoadingState } from '../../shared/ui/DataState';
import {
  AGGRESSIVE_BANNER_CROP_SPEC,
  ImageCropEditor,
  NATIVE_BANNER_CROP_SPEC,
  type ImageCropSpec,
} from '../../shared/ui/ImageCropEditor';
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
  displayType: BannerDisplayType;
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
  displayType: 'horizontal',
  position: '0',
  isActive: false,
  startsAt: '',
  endsAt: '',
};

export function BannersPage({ onAuthExpired }: PageProps) {
  const { language, t } = useI18n();
  const [banners, setBanners] = useState<Banner[]>([]);
  const [editingBanner, setEditingBanner] = useState<Banner | null>(null);
  const [form, setForm] = useState<BannerFormState>(initialForm);
  const [imageFile, setImageFile] = useState<File | null>(null);
  const [cropSourceFile, setCropSourceFile] = useState<File | null>(null);
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
      displayType: banner.display_type ?? 'horizontal',
      position: String(banner.position),
      isActive: banner.is_active,
      startsAt: toDateTimeInput(banner.starts_at),
      endsAt: toDateTimeInput(banner.ends_at),
    });
    setImageFile(null);
    setCropSourceFile(null);
    setFormError(null);
  }

  function resetForm() {
    setEditingBanner(null);
    setForm(initialForm);
    setImageFile(null);
    setCropSourceFile(null);
    setFormError(null);
  }

  function handleImageChange(event: ChangeEvent<HTMLInputElement>) {
    setCropSourceFile(event.target.files?.[0] ?? null);
    event.target.value = '';
  }

  function handleBannerCropApply(file: File) {
    setImageFile(file);
    setCropSourceFile(null);
  }

  function handleBannerCropCancel() {
    setCropSourceFile(null);
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSaving(true);
    setFormError(null);
    setNotice(null);

    try {
      let imagePath = form.imagePath.trim();
      if (imageFile) {
        const uploaded = await api.banners.uploadImage(
          imageFile,
          form.title,
          getBannerImageKind(form.targetType, form.displayType),
        );
        imagePath = uploaded.file_path;
      }

      if (!imagePath) {
        setFormError(t('banners.imageRequired'));
        return;
      }

      if (form.targetType === 'external_url' && !form.externalUrl.trim()) {
        setFormError(t('banners.externalRequired'));
        return;
      }

      if ((form.targetType === 'product' || form.targetType === 'category') && !form.targetId.trim()) {
        setFormError(t('banners.targetRequired'));
        return;
      }

      const payload: BannerPayload = {
        title: form.title.trim(),
        subtitle: form.subtitle.trim() || null,
        image_path: imagePath,
        target_type: form.targetType,
        target_id:
          form.targetType === 'external_url' || !form.targetId.trim() ? null : Number(form.targetId),
        external_url: form.targetType === 'external_url' ? form.externalUrl.trim() || null : null,
        display_type: form.displayType,
        position: Number(form.position || 0),
        is_active: form.isActive,
        starts_at: fromDateTimeInput(form.startsAt),
        ends_at: fromDateTimeInput(form.endsAt),
      };

      if (editingBanner) {
        await api.banners.update(editingBanner.id, payload);
        setNotice(t('banners.updated'));
      } else {
        await api.banners.create(payload);
        setNotice(t('banners.created'));
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

  if (loading) return <LoadingState title={t('banners.loading')} />;
  if (error) {
    return <ErrorState error={error} onRetry={loadBanners} onAuthExpired={onAuthExpired} />;
  }
  const bannerCropSpec = getBannerCropSpec(form.targetType, form.displayType);

  return (
    <div className="split-view">
      <div className="page-stack">
        {notice ? <div className="success-banner">{notice}</div> : null}
        <div className="table-panel">
          <table>
            <thead>
              <tr>
                <th>{t('banners.preview')}</th>
                <th>{t('common.title')}</th>
                <th>{t('banners.target')}</th>
                <th>{t('banners.displayType')}</th>
                <th>{t('banners.position')}</th>
                <th>{t('common.status')}</th>
                <th>{t('banners.dates')}</th>
                <th>{t('common.actions')}</th>
              </tr>
            </thead>
            <tbody>
              {banners.length === 0 ? (
                <tr>
                  <td colSpan={8}>
                    <div className="empty-table">{t('banners.empty')}</div>
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
                      <small>{banner.subtitle ?? t('banners.noSubtitle')}</small>
                    </td>
                    <td>
                      <span>{labelForEnum(banner.target_type, t)}</span>
                      <small>
                        {banner.target_type === 'external_url'
                          ? banner.external_url
                          : banner.target_id ?? t('banners.noTarget')}
                      </small>
                    </td>
                    <td>{labelForEnum(banner.display_type, t)}</td>
                    <td>{banner.position}</td>
                    <td>
                      <StatusBadge status={banner.is_active ? 'ACTIVE' : 'INACTIVE'} />
                    </td>
                    <td>
                      <small>{formatDate(banner.starts_at, language)}</small>
                      <small>{formatDate(banner.ends_at, language)}</small>
                    </td>
                    <td>
                      <div className="table-actions">
                        <button className="text-button" type="button" onClick={() => selectBanner(banner)}>
                          {t('common.edit')}
                        </button>
                        <button className="text-button" type="button" onClick={() => toggleBanner(banner)}>
                          {banner.is_active ? t('common.deactivate') : t('common.activate')}
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
          <h2>{editingBanner ? t('banners.edit') : t('banners.create')}</h2>
          {editingBanner ? (
            <button className="text-button" type="button" onClick={resetForm}>
              {t('common.new')}
            </button>
          ) : null}
        </div>
        {formError ? <div className="form-error">{formError}</div> : null}
        <form className="form-stack" onSubmit={handleSubmit}>
          <label className="field">
            <span>{t('common.title')}</span>
            <input
              value={form.title}
              onChange={(event) => setForm((current) => ({ ...current, title: event.target.value }))}
            />
          </label>
          <label className="field">
            <span>{t('common.subtitle')}</span>
            <input
              value={form.subtitle}
              onChange={(event) =>
                setForm((current) => ({ ...current, subtitle: event.target.value }))
              }
            />
          </label>
          <label className="field">
            <span>{t('banners.imageFile')}</span>
            <p className="image-hints image-hints-current">
              {t('banners.cropHint', {
                width: bannerCropSpec.outputWidth,
                height: bannerCropSpec.outputHeight,
                minWidth: bannerCropSpec.minWidth,
                minHeight: bannerCropSpec.minHeight,
              })}
            </p>
            {form.displayType === 'aggressive_popup' ? (
              <p className="image-hints">{t('banners.aggressiveHint')}</p>
            ) : null}
            <p className="image-hints">
              Рекомендуемый размер: {bannerCropSpec.outputWidth}x{bannerCropSpec.outputHeight}.
              Минимальный размер: {bannerCropSpec.minWidth}x{bannerCropSpec.minHeight}.
            </p>
            <input accept="image/*" type="file" onChange={handleImageChange} />
          </label>
          {imageFile ? (
            <div className="upload-list">
              <span>
                {imageFile.name}
                <button
                  className="text-button danger-text"
                  type="button"
                  onClick={() => setImageFile(null)}
                >
                  {t('common.remove')}
                </button>
              </span>
            </div>
          ) : null}
          <label className="field">
            <span>{t('banners.imagePath')}</span>
            <input
              value={form.imagePath}
              onChange={(event) =>
                setForm((current) => ({ ...current, imagePath: event.target.value }))
              }
              placeholder={t('banners.imagePathPlaceholder')}
            />
          </label>
          <label className="field">
            <span>{t('banners.targetType')}</span>
            <select
              value={form.targetType}
              onChange={(event) =>
                setForm((current) => ({
                  ...current,
                  targetType: event.target.value as BannerTargetType,
                }))
              }
            >
              <option value="product">{labelForEnum('product', t)}</option>
              <option value="category">{labelForEnum('category', t)}</option>
              <option value="promo">{labelForEnum('promo', t)}</option>
              <option value="external_url">{labelForEnum('external_url', t)}</option>
            </select>
          </label>
          <label className="field">
            <span>{t('banners.targetId')}</span>
            <input
              type="number"
              value={form.targetId}
              onChange={(event) =>
                setForm((current) => ({ ...current, targetId: event.target.value }))
              }
            />
            {form.targetType === 'promo' ? (
              <small className="field-hint">{t('banners.targetIdHint')}</small>
            ) : null}
          </label>
          {form.targetType === 'external_url' ? (
            <label className="field">
              <span>{t('common.externalUrl')}</span>
              <input
                value={form.externalUrl}
                onChange={(event) =>
                  setForm((current) => ({ ...current, externalUrl: event.target.value }))
                }
              />
            </label>
          ) : null}
          <label className="field">
            <span>{t('banners.displayType')}</span>
            <select
              value={form.displayType}
              onChange={(event) =>
                setForm((current) => ({
                  ...current,
                  displayType: event.target.value as BannerDisplayType,
                }))
              }
            >
              <option value="horizontal">{labelForEnum('horizontal', t)}</option>
              <option value="vertical">{labelForEnum('vertical', t)}</option>
              <option value="popup">{labelForEnum('popup', t)}</option>
              <option value="aggressive_popup">{labelForEnum('aggressive_popup', t)}</option>
            </select>
          </label>
          <label className="field">
            <span>{t('banners.position')}</span>
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
          {form.title || form.subtitle ? (
            <div className="banner-preview">
              <strong>{form.title || t('banners.titlePlaceholder')}</strong>
              <span>{form.subtitle || t('banners.subtitlePlaceholder')}</span>
            </div>
          ) : null}
          <button className="button button-primary" disabled={saving} type="submit">
            {saving ? t('common.saving') : editingBanner ? t('banners.save') : t('banners.createButton')}
          </button>
        </form>
      </aside>
      {cropSourceFile ? (
        <ImageCropEditor
          file={cropSourceFile}
          spec={bannerCropSpec}
          onApply={handleBannerCropApply}
          onCancel={handleBannerCropCancel}
        />
      ) : null}
    </div>
  );
}

function getBannerCropSpec(
  targetType: BannerTargetType,
  displayType: BannerDisplayType,
): ImageCropSpec {
  return targetType === 'promo' || displayType === 'aggressive_popup'
    ? AGGRESSIVE_BANNER_CROP_SPEC
    : NATIVE_BANNER_CROP_SPEC;
}

function getBannerImageKind(
  targetType: BannerTargetType,
  displayType: BannerDisplayType,
): BannerImageKind {
  return targetType === 'promo' || displayType === 'aggressive_popup'
    ? 'aggressive_banner'
    : 'native_banner';
}
