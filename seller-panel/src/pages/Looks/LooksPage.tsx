import { ChangeEvent, FormEvent, useEffect, useMemo, useRef, useState } from 'react';
import { ApiError, api, resolveMediaUrl } from '../../shared/api';
import type {
  Look,
  LookCreatePayload,
  LookItemPayload,
  LookStatus,
  Product,
} from '../../shared/api';
import { useI18n } from '../../shared/i18n';
import { ErrorState, LoadingState } from '../../shared/ui/DataState';
import { StatusBadge } from '../../shared/ui/StatusBadge';
import { compactText, formatDate, formatMoney } from '../../shared/utils/format';
import { applyGeneratedLookSlug } from './lookSlugAutofill';

interface PageProps {
  onNavigate: (path: string) => void;
  onAuthExpired: () => void;
}

interface EditorProps extends PageProps {
  mode: 'create' | 'edit';
  lookId?: number;
}

interface LookFormState {
  title: string;
  slug: string;
  description: string;
  status: LookStatus;
  isListed: boolean;
  searchPriority: '1' | '2' | '3';
}

interface LookItemRow {
  localId: number;
  id?: number;
  productId: number;
  quantity: number;
  isDefaultSelected: boolean;
}

const lookStatuses: LookStatus[] = ['DRAFT', 'ACTIVE', 'ARCHIVED'];
const slugPattern = /^[a-z0-9]+(?:-[a-z0-9]+)*$/;

const initialLookForm: LookFormState = {
  title: '',
  slug: '',
  description: '',
  status: 'DRAFT',
  isListed: true,
  searchPriority: '1',
};

export function LooksPage({ onNavigate, onAuthExpired }: PageProps) {
  const { language, t } = useI18n();
  const [looks, setLooks] = useState<Look[]>([]);
  const [products, setProducts] = useState<Product[]>([]);
  const [statusFilter, setStatusFilter] = useState<'' | LookStatus>('');
  const [search, setSearch] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<unknown>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const productMap = useMemo(() => buildProductMap(products), [products]);
  const filteredLooks = useMemo(() => {
    const needle = search.trim().toLowerCase();
    return looks.filter((look) => {
      if (statusFilter && look.status !== statusFilter) {
        return false;
      }
      if (!needle) {
        return true;
      }
      return look.title.toLowerCase().includes(needle) || look.slug.toLowerCase().includes(needle);
    });
  }, [looks, search, statusFilter]);

  function loadLooks() {
    setLoading(true);
    setError(null);
    Promise.all([
      api.looks.listAdmin({ limit: 100, offset: 0 }),
      api.products.listAdmin({ limit: 100, offset: 0 }),
    ])
      .then(([lookList, productList]) => {
        setLooks(lookList.items);
        setProducts(productList.items);
      })
      .catch(setError)
      .finally(() => setLoading(false));
  }

  useEffect(() => {
    loadLooks();
  }, []);

  async function archiveLook(look: Look) {
    if (!window.confirm(t('looks.archiveConfirm', { title: look.title }))) {
      return;
    }

    setNotice(null);
    try {
      await api.looks.archive(look.id);
      setNotice(t('looks.archived'));
      loadLooks();
    } catch (requestError) {
      setError(requestError);
    }
  }

  if (loading) return <LoadingState title={t('looks.loading')} />;
  if (error) {
    return <ErrorState error={error} onRetry={loadLooks} onAuthExpired={onAuthExpired} />;
  }

  return (
    <div className="page-stack looks-page">
      <div className="page-toolbar">
        <div className="filters-row">
          <label>
            <span>{t('common.status')}</span>
            <select
              value={statusFilter}
              onChange={(event) => setStatusFilter(event.target.value as '' | LookStatus)}
            >
              <option value="">{t('common.all')}</option>
              {lookStatuses.map((status) => (
                <option value={status} key={status}>
                  {lookStatusLabel(status, t)}
                </option>
              ))}
            </select>
          </label>
          <label>
            <span>{t('common.search')}</span>
            <input
              value={search}
              placeholder={t('looks.searchPlaceholder')}
              onChange={(event) => setSearch(event.target.value)}
            />
          </label>
        </div>
        <button className="button button-primary" type="button" onClick={() => onNavigate('/looks/new')}>
          {t('looks.create')}
        </button>
      </div>

      {notice ? <div className="success-banner">{notice}</div> : null}

      <div className="table-panel looks-table-panel">
        <table>
          <thead>
            <tr>
              <th>{t('common.image')}</th>
              <th>{t('looks.look')}</th>
              <th>{t('common.status')}</th>
              <th>{t('looks.items')}</th>
              <th>{t('looks.defaultPrice')}</th>
              <th>{t('common.updated')}</th>
              <th>{t('common.actions')}</th>
            </tr>
          </thead>
          <tbody>
            {filteredLooks.length === 0 ? (
              <tr>
                <td colSpan={7}>
                  <div className="empty-table">{t('looks.empty')}</div>
                </td>
              </tr>
            ) : (
              filteredLooks.map((look) => {
                const primaryImage = getLookPrimaryImageUrl(look);
                const defaultPrice = calculateLookDefaultPrice(look, productMap);
                return (
                  <tr key={look.id}>
                    <td>
                      {primaryImage ? (
                        <img
                          className="table-image look-table-image"
                          src={resolveMediaUrl(primaryImage)}
                          alt={look.title}
                          loading="lazy"
                          decoding="async"
                        />
                      ) : (
                        <div className="table-image table-image-empty">{t('looks.noImage')}</div>
                      )}
                    </td>
                    <td>
                      <strong>{look.title}</strong>
                      <small>{look.slug}</small>
                      {!look.is_listed ? (
                        <span className="product-state-badge">{t('looks.hiddenBadge')}</span>
                      ) : null}
                    </td>
                    <td>
                      <StatusBadge status={look.status} label={lookStatusLabel(look.status, t)} />
                    </td>
                    <td>{look.items.length}</td>
                    <td>{formatMoney(defaultPrice, language)}</td>
                    <td>
                      {formatDate(look.updated_at, language)}
                      <small>{t('common.created')}: {formatDate(look.created_at, language)}</small>
                    </td>
                    <td>
                      <div className="table-actions">
                        <button
                          className="text-button"
                          type="button"
                          onClick={() => onNavigate(`/looks/${look.id}/edit`)}
                        >
                          {t('common.edit')}
                        </button>
                        <button
                          className="text-button danger-text"
                          disabled={look.status === 'ARCHIVED'}
                          type="button"
                          onClick={() => void archiveLook(look)}
                        >
                          {t('common.archive')}
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export function LookEditorPage({ mode, lookId, onNavigate, onAuthExpired }: EditorProps) {
  const { language, t } = useI18n();
  const [form, setForm] = useState<LookFormState>(initialLookForm);
  const [look, setLook] = useState<Look | null>(null);
  const [products, setProducts] = useState<Product[]>([]);
  const [items, setItems] = useState<LookItemRow[]>([]);
  const [selectedProductId, setSelectedProductId] = useState('');
  const [loading, setLoading] = useState(mode === 'edit');
  const [saving, setSaving] = useState(false);
  const [imageBusy, setImageBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const manualSlugEditRef = useRef(false);

  const productMap = useMemo(() => buildProductMap(products), [products]);
  const availableProductsForSelect = useMemo(() => {
    const selectedIds = new Set(items.map((item) => item.productId));
    return products.filter((product) => !selectedIds.has(product.id));
  }, [items, products]);
  const defaultPrice = useMemo(
    () => calculateRowsDefaultPrice(items, productMap),
    [items, productMap],
  );
  const hasDefaultSelection = items.some((item) => item.isDefaultSelected);
  const activeLookWarnings = useMemo(
    () => buildLookWarnings(form, items, productMap, t),
    [form, items, productMap, t],
  );

  function loadNextLookSlug() {
    if (mode !== 'create') {
      return;
    }

    api.looks.getNextSlugs(1)
      .then((response) => {
        const nextSlug = response.items[0];
        setForm((current) => ({
          ...current,
          slug: applyGeneratedLookSlug({
            mode,
            currentSlug: current.slug,
            generatedSlug: nextSlug,
            wasManuallyEdited: manualSlugEditRef.current,
          }),
        }));
      })
      .catch(() => {
        setFormError(t('looks.slugAutofillFailed'));
      });
  }

  function loadEditor() {
    setLoading(true);
    setError(null);

    Promise.all([
      api.products.listAdmin({ limit: 100, offset: 0 }),
      mode === 'edit' && lookId ? api.looks.getAdmin(lookId) : Promise.resolve(null),
    ])
      .then(([productList, loadedLook]) => {
        setProducts(productList.items);
        if (loadedLook) {
          manualSlugEditRef.current = true;
          setLook(loadedLook);
          setForm({
            title: loadedLook.title,
            slug: loadedLook.slug,
            description: loadedLook.description ?? '',
            status: loadedLook.status,
            isListed: loadedLook.is_listed,
            searchPriority: String(loadedLook.search_priority ?? 1) as LookFormState['searchPriority'],
          });
          setItems(
            loadedLook.items
              .slice()
              .sort((left, right) => left.position - right.position)
              .map((item) => ({
                localId: item.id,
                id: item.id,
                productId: item.product_id,
                quantity: item.quantity,
                isDefaultSelected: item.is_default_selected,
              })),
          );
        } else {
          manualSlugEditRef.current = false;
          setLook(null);
          setForm(initialLookForm);
          setItems([]);
          loadNextLookSlug();
        }
      })
      .catch(setError)
      .finally(() => setLoading(false));
  }

  useEffect(() => {
    loadEditor();
  }, [mode, lookId]);

  function updateField<Key extends keyof LookFormState>(key: Key, value: LookFormState[Key]) {
    setForm((current) => ({ ...current, [key]: value }));
  }

  function addProductToLook() {
    const productId = Number(selectedProductId);
    if (!Number.isInteger(productId) || productId <= 0) {
      setFormError(t('looks.selectProduct'));
      return;
    }
    if (items.some((item) => item.productId === productId)) {
      setFormError(t('looks.duplicateProduct'));
      return;
    }
    setItems((current) => [
      ...current,
      {
        localId: Date.now() + Math.random(),
        productId,
        quantity: 1,
        isDefaultSelected: true,
      },
    ]);
    setSelectedProductId('');
    setFormError(null);
  }

  function updateItem(localId: number, patch: Partial<LookItemRow>) {
    setItems((current) =>
      current.map((item) => (item.localId === localId ? { ...item, ...patch } : item)),
    );
  }

  function removeItem(localId: number) {
    setItems((current) => current.filter((item) => item.localId !== localId));
  }

  function moveItem(index: number, direction: -1 | 1) {
    setItems((current) => {
      const targetIndex = index + direction;
      if (targetIndex < 0 || targetIndex >= current.length) {
        return current;
      }
      const next = [...current];
      [next[index], next[targetIndex]] = [next[targetIndex], next[index]];
      return next;
    });
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await saveLook(true);
  }

  async function saveLook(stayOnPage: boolean) {
    setSaving(true);
    setError(null);
    setFormError(null);
    setSuccess(null);

    const validationError = validateLookForm(form, items, productMap, t);
    if (validationError) {
      setFormError(validationError);
      setSaving(false);
      return;
    }

    const payload = buildLookPayload(form, items);
    try {
      const savedLook =
        mode === 'edit' && lookId
          ? await api.looks.update(lookId, payload)
          : await api.looks.create(payload);

      if (!stayOnPage) {
        onNavigate('/looks');
        return;
      }

      setSuccess(t('looks.saved', { title: savedLook.title }));
      if (mode === 'create') {
        onNavigate(`/looks/${savedLook.id}/edit`);
        return;
      }
      setLook(savedLook);
      setItems(
        savedLook.items
          .slice()
          .sort((left, right) => left.position - right.position)
          .map((item) => ({
            localId: item.id,
            id: item.id,
            productId: item.product_id,
            quantity: item.quantity,
            isDefaultSelected: item.is_default_selected,
          })),
      );
    } catch (requestError) {
      setFormError(formatRequestError(requestError));
    } finally {
      setSaving(false);
    }
  }

  async function archiveCurrentLook() {
    if (!look || !window.confirm(t('looks.archiveConfirm', { title: look.title }))) {
      return;
    }
    setSaving(true);
    setFormError(null);
    try {
      const archived = await api.looks.archive(look.id);
      setLook(archived);
      setForm((current) => ({ ...current, status: archived.status }));
      setSuccess(t('looks.archived'));
    } catch (requestError) {
      setFormError(formatRequestError(requestError));
    } finally {
      setSaving(false);
    }
  }

  async function handleImageSelection(event: ChangeEvent<HTMLInputElement>) {
    const files = Array.from(event.target.files ?? []);
    event.target.value = '';
    if (!look || files.length === 0) {
      return;
    }

    setImageBusy(true);
    setFormError(null);
    try {
      for (let index = 0; index < files.length; index += 1) {
        await api.looks.uploadImage(look.id, files[index], {
          position: look.images.length + index,
          isPrimary: look.images.length === 0 && index === 0,
        });
      }
      const reloaded = await api.looks.getAdmin(look.id);
      setLook(reloaded);
      setSuccess(t('looks.imageUploaded'));
    } catch (requestError) {
      setFormError(formatRequestError(requestError));
    } finally {
      setImageBusy(false);
    }
  }

  async function deleteImage(imageId: number) {
    if (!look) {
      return;
    }
    setImageBusy(true);
    setFormError(null);
    try {
      await api.looks.deleteImage(look.id, imageId);
      const reloaded = await api.looks.getAdmin(look.id);
      setLook(reloaded);
      setSuccess(t('looks.imageDeleted'));
    } catch (requestError) {
      setFormError(formatRequestError(requestError));
    } finally {
      setImageBusy(false);
    }
  }

  if (loading) return <LoadingState title={t('looks.editorLoading')} />;
  if (error) {
    return <ErrorState error={error} onRetry={loadEditor} onAuthExpired={onAuthExpired} />;
  }

  return (
    <form className="page-stack looks-editor" onSubmit={handleSubmit}>
      {formError ? <div className="form-error">{formError}</div> : null}
      {success ? <div className="success-banner">{success}</div> : null}

      <div className="form-layout">
        <section className="panel">
          <div className="section-heading">
            <div>
              <h2>{t('looks.basicInfo')}</h2>
              <p>{t('looks.slugHint')}</p>
            </div>
            {look ? <StatusBadge status={look.status} label={lookStatusLabel(look.status, t)} /> : null}
          </div>
          <div className="form-grid">
            <label className="field">
              <span>{t('looks.title')}</span>
              <input
                value={form.title}
                onChange={(event) => updateField('title', event.target.value)}
              />
            </label>
            <label className="field">
              <span>{t('looks.slug')}</span>
              <input
                value={form.slug}
                onChange={(event) => {
                  manualSlugEditRef.current = true;
                  updateField('slug', event.target.value);
                }}
              />
              <small className="field-hint">{t('looks.slugInputHint')}</small>
            </label>
            <div className="form-pair-row field-wide">
              <label className="field">
                <span>{t('common.status')}</span>
                <select
                  value={form.status}
                  onChange={(event) => updateField('status', event.target.value as LookStatus)}
                >
                  {lookStatuses.map((status) => (
                    <option value={status} key={status}>
                      {lookStatusLabel(status, t)}
                    </option>
                  ))}
                </select>
              </label>
              <label className="field">
                <span>{t('looks.searchPriority')}</span>
                <select
                  value={form.searchPriority}
                  onChange={(event) =>
                    updateField(
                      'searchPriority',
                      event.target.value as LookFormState['searchPriority'],
                    )
                  }
                >
                  <option value="1">{t('productEditor.priorityHigh')}</option>
                  <option value="2">{t('productEditor.priorityMedium')}</option>
                  <option value="3">{t('productEditor.priorityLow')}</option>
                </select>
              </label>
            </div>
            <label className="toggle-label product-setting-toggle field-wide">
              <input
                checked={form.isListed}
                type="checkbox"
                onChange={(event) => updateField('isListed', event.target.checked)}
              />
              <span>{t('looks.isListed')}</span>
            </label>
            <label className="field field-wide">
              <span>{t('common.description')}</span>
              <textarea
                rows={5}
                value={form.description}
                onChange={(event) => updateField('description', event.target.value)}
              />
            </label>
          </div>
        </section>

        <aside className="panel compact-panel">
          <h2>{t('looks.summary')}</h2>
          <dl className="details-list">
            <div><dt>ID</dt><dd>{look?.id ?? t('common.new')}</dd></div>
            <div><dt>{t('looks.items')}</dt><dd>{items.length}</dd></div>
            <div><dt>{t('looks.defaultPrice')}</dt><dd>{formatMoney(defaultPrice, language)}</dd></div>
            <div><dt>{t('looks.defaultSelected')}</dt><dd>{hasDefaultSelection ? t('common.yes') : t('common.no')}</dd></div>
            {look ? (
              <>
                <div><dt>{t('common.created')}</dt><dd>{formatDate(look.created_at, language)}</dd></div>
                <div><dt>{t('common.updated')}</dt><dd>{formatDate(look.updated_at, language)}</dd></div>
              </>
            ) : null}
          </dl>
          {activeLookWarnings.length > 0 ? (
            <div className="warning-list">
              {activeLookWarnings.map((warning) => <p key={warning}>{warning}</p>)}
            </div>
          ) : null}
        </aside>
      </div>

      <section className="panel">
        <div className="section-heading">
          <div>
            <h2>{t('looks.productsSection')}</h2>
            <p>{t('looks.productsHint')}</p>
          </div>
        </div>

        <div className="look-product-picker">
          <label className="field">
            <span>{t('looks.addProduct')}</span>
            <select
              value={selectedProductId}
              onChange={(event) => setSelectedProductId(event.target.value)}
            >
              <option value="">{t('looks.selectProduct')}</option>
              {availableProductsForSelect.map((product) => (
                <option key={product.id} value={product.id}>
                  {formatProductOption(product)}
                </option>
              ))}
            </select>
          </label>
          <button className="button button-secondary" type="button" onClick={addProductToLook}>
            {t('common.add')}
          </button>
        </div>

        <div className="look-item-list">
          {items.length === 0 ? (
            <div className="empty-table">{t('looks.noProducts')}</div>
          ) : (
            items.map((item, index) => {
              const product = productMap.get(item.productId);
              return (
                <LookItemCard
                  index={index}
                  item={item}
                  itemCount={items.length}
                  key={item.localId}
                  product={product}
                  onMove={moveItem}
                  onRemove={removeItem}
                  onUpdate={updateItem}
                />
              );
            })
          )}
        </div>
      </section>

      <section className="panel">
        <div className="section-heading">
          <h2>{t('looks.imagesSection')}</h2>
        </div>
        {!look ? (
          <p className="muted-text">{t('looks.saveBeforeImages')}</p>
        ) : (
          <div className="look-images-panel">
            <div className="look-image-grid">
              {look.images.length === 0 ? (
                <div className="empty-table">{t('looks.noImages')}</div>
              ) : (
                look.images
                  .slice()
                  .sort((left, right) => left.position - right.position)
                  .map((image) => (
                    <figure className="look-image-card" key={image.id}>
                      <img
                        src={resolveMediaUrl(image.image_url ?? image.url ?? image.file_path)}
                        alt={image.alt_text ?? look.title}
                        loading="lazy"
                        decoding="async"
                      />
                      <figcaption>
                        {image.is_primary ? <span>{t('looks.primaryImage')}</span> : null}
                        <button
                          className="text-button danger-text"
                          disabled={imageBusy}
                          type="button"
                          onClick={() => void deleteImage(image.id)}
                        >
                          {t('common.delete')}
                        </button>
                      </figcaption>
                    </figure>
                  ))
              )}
            </div>
            <label className="button button-secondary look-upload-button">
              {imageBusy ? t('common.saving') : t('looks.uploadImage')}
              <input
                accept="image/jpeg,image/png,image/webp"
                disabled={imageBusy}
                multiple
                type="file"
                onChange={handleImageSelection}
              />
            </label>
          </div>
        )}
      </section>

      <section className="panel">
        <div className="form-actions">
          {look ? (
            <button
              className="button button-danger"
              disabled={saving}
              type="button"
              onClick={() => void archiveCurrentLook()}
            >
              {t('common.archive')}
            </button>
          ) : null}
          <button className="button button-secondary" type="button" onClick={() => onNavigate('/looks')}>
            {t('common.cancel')}
          </button>
          <button
            className="button button-secondary"
            disabled={saving}
            type="button"
            onClick={() => void saveLook(false)}
          >
            {saving ? t('common.saving') : t('looks.save')}
          </button>
          <button className="button button-primary" disabled={saving} type="submit">
            {saving ? t('common.saving') : t('looks.saveStay')}
          </button>
        </div>
      </section>
    </form>
  );
}

function LookItemCard({
  index,
  item,
  itemCount,
  product,
  onMove,
  onRemove,
  onUpdate,
}: {
  index: number;
  item: LookItemRow;
  itemCount: number;
  product: Product | undefined;
  onMove: (index: number, direction: -1 | 1) => void;
  onRemove: (localId: number) => void;
  onUpdate: (localId: number, patch: Partial<LookItemRow>) => void;
}) {
  const { language, t } = useI18n();

  if (!product) {
    return (
      <article className="look-item-card">
        <div className="look-item-main">
          <strong>{t('looks.productMissing', { id: item.productId })}</strong>
        </div>
        <button
          className="text-button danger-text"
          type="button"
          onClick={() => onRemove(item.localId)}
        >
          {t('common.remove')}
        </button>
      </article>
    );
  }

  const image = product.images.find((itemImage) => itemImage.is_primary) ?? product.images[0];
  const activeColors = getActiveColors(product);
  const activeSizes = getActiveSizes(product);
  const activeSkus = product.variants
    .filter((variant) => variant.is_active)
    .map((variant) => variant.sku)
    .slice(0, 3);
  const hasColorWarning = activeColors.length > 1;

  return (
    <article className="look-item-card">
      <div className="look-item-order">
        <strong>{index + 1}</strong>
        <button
          className="text-button"
          disabled={index === 0}
          type="button"
          onClick={() => onMove(index, -1)}
        >
          {t('looks.moveUp')}
        </button>
        <button
          className="text-button"
          disabled={index === itemCount - 1}
          type="button"
          onClick={() => onMove(index, 1)}
        >
          {t('looks.moveDown')}
        </button>
      </div>
      {image ? (
        <img
          className="look-product-thumb"
          src={resolveMediaUrl(image.thumbnail_url ?? image.card_url ?? image.url)}
          alt={image.alt_text ?? product.name}
          loading="lazy"
          decoding="async"
        />
      ) : (
        <div className="look-product-thumb look-product-thumb-empty">{t('products.noImage')}</div>
      )}
      <div className="look-item-main">
        <div className="look-item-title-row">
          <div>
            <strong>{product.name}</strong>
            <small>{[product.brand, product.slug].filter(Boolean).join(' · ')}</small>
          </div>
          <StatusBadge status={product.status} />
        </div>
        <div className="product-state-badges">
          {!product.is_listed ? (
            <span className="product-state-badge">{t('looks.hiddenBadge')}</span>
          ) : null}
          {hasColorWarning ? (
            <span className="product-state-badge product-state-badge-warning">
              {t('looks.multiColorWarning')}
            </span>
          ) : null}
        </div>
        <div className="look-product-meta">
          <span>{formatMoney(product.base_price, language)}</span>
          <span>{t('looks.skus')}: {activeSkus.join(', ') || t('common.none')}</span>
          <span>{t('looks.colors')}: {activeColors.join(', ') || t('productEditor.noColor')}</span>
          <span>{t('looks.sizes')}: {activeSizes.join(', ') || t('common.none')}</span>
        </div>
      </div>
      <div className="look-item-controls">
        <label className="field">
          <span>{t('looks.quantity')}</span>
          <input
            min="1"
            type="number"
            value={item.quantity}
            onChange={(event) =>
              onUpdate(item.localId, { quantity: Number(event.target.value) })
            }
          />
        </label>
        <label className="toggle-label look-default-toggle">
          <input
            checked={item.isDefaultSelected}
            type="checkbox"
            onChange={(event) =>
              onUpdate(item.localId, { isDefaultSelected: event.target.checked })
            }
          />
          <span>{t('looks.defaultSelected')}</span>
        </label>
        <button
          className="text-button danger-text"
          type="button"
          onClick={() => onRemove(item.localId)}
        >
          {t('common.remove')}
        </button>
      </div>
    </article>
  );
}

function buildProductMap(products: Product[]): Map<number, Product> {
  return new Map(products.map((product) => [product.id, product]));
}

function getLookPrimaryImageUrl(look: Look): string | null {
  const image = look.images.find((item) => item.is_primary) ?? look.images[0];
  return image?.image_url ?? image?.url ?? image?.file_path ?? null;
}

function calculateLookDefaultPrice(look: Look, productMap: Map<number, Product>): number {
  return look.items
    .filter((item) => item.is_default_selected)
    .reduce((sum, item) => {
      const product = productMap.get(item.product_id);
      return sum + Number(product?.base_price ?? 0) * item.quantity;
    }, 0);
}

function calculateRowsDefaultPrice(items: LookItemRow[], productMap: Map<number, Product>): number {
  return items
    .filter((item) => item.isDefaultSelected)
    .reduce((sum, item) => {
      const product = productMap.get(item.productId);
      return sum + Number(product?.base_price ?? 0) * item.quantity;
    }, 0);
}

function buildLookPayload(form: LookFormState, items: LookItemRow[]): LookCreatePayload {
  return {
    title: form.title.trim(),
    slug: form.slug.trim(),
    description: form.description.trim() || null,
    status: form.status,
    is_listed: form.isListed,
    search_priority: Number(form.searchPriority) as 1 | 2 | 3,
    items: items.map((item, index): LookItemPayload => ({
      product_id: item.productId,
      position: index,
      quantity: item.quantity,
      is_default_selected: item.isDefaultSelected,
    })),
  };
}

function validateLookForm(
  form: LookFormState,
  items: LookItemRow[],
  productMap: Map<number, Product>,
  t: (key: string, params?: Record<string, string | number | null | undefined>) => string,
): string | null {
  if (!form.title.trim()) {
    return t('looks.titleRequired');
  }
  if (!form.slug.trim()) {
    return t('looks.slugRequired');
  }
  if (!slugPattern.test(form.slug.trim())) {
    return t('looks.slugInvalid');
  }
  if (items.some((item) => !Number.isInteger(item.quantity) || item.quantity < 1)) {
    return t('looks.quantityInvalid');
  }
  if (new Set(items.map((item) => item.productId)).size !== items.length) {
    return t('looks.duplicateProduct');
  }
  const multiColorProduct = items
    .map((item) => productMap.get(item.productId))
    .find((product) => product && hasMultipleActiveColors(product));
  if (multiColorProduct) {
    return t('looks.multiColorWarning');
  }
  if (form.status === 'ACTIVE') {
    if (items.length === 0) {
      return t('looks.activeNeedsProduct');
    }
    if (!items.some((item) => item.isDefaultSelected)) {
      return t('looks.activeNeedsDefault');
    }
    const inactiveProduct = items
      .map((item) => productMap.get(item.productId))
      .find((product) => product && product.status !== 'ACTIVE');
    if (inactiveProduct) {
      return t('looks.activeNeedsActiveProducts');
    }
  }
  return null;
}

function buildLookWarnings(
  form: LookFormState,
  items: LookItemRow[],
  productMap: Map<number, Product>,
  t: (key: string, params?: Record<string, string | number | null | undefined>) => string,
): string[] {
  const warnings: string[] = [];
  if (form.status === 'ACTIVE' && items.length === 0) {
    warnings.push(t('looks.activeNeedsProduct'));
  }
  if (form.status === 'ACTIVE' && !items.some((item) => item.isDefaultSelected)) {
    warnings.push(t('looks.activeNeedsDefault'));
  }
  if (
    form.status === 'ACTIVE' &&
    items.some((item) => {
      const product = productMap.get(item.productId);
      return product && product.status !== 'ACTIVE';
    })
  ) {
    warnings.push(t('looks.activeNeedsActiveProducts'));
  }
  if (
    items.some((item) => {
      const product = productMap.get(item.productId);
      return product && hasMultipleActiveColors(product);
    })
  ) {
    warnings.push(t('looks.multiColorWarning'));
  }
  return warnings;
}

function getActiveColors(product: Product): string[] {
  return Array.from(
    new Set(
      product.variants
        .filter((variant) => variant.is_active && variant.color?.trim())
        .map((variant) => variant.color?.trim() ?? ''),
    ),
  );
}

function getActiveSizes(product: Product): string[] {
  return Array.from(
    new Set(
      product.variants
        .filter((variant) => variant.is_active)
        .map((variant) => variant.size)
        .filter(Boolean),
    ),
  ).sort();
}

function hasMultipleActiveColors(product: Product): boolean {
  return getActiveColors(product).length > 1;
}

function formatProductOption(product: Product): string {
  return `${product.name} - ${product.slug}`;
}

function lookStatusLabel(
  status: LookStatus,
  t: (key: string, params?: Record<string, string | number | null | undefined>) => string,
): string {
  return t(`looks.status.${status}`);
}

function formatRequestError(error: unknown): string {
  if (error instanceof ApiError) {
    return error.message;
  }
  return error instanceof Error ? error.message : 'Request failed';
}
