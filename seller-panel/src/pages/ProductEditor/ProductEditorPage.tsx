import { ChangeEvent, FormEvent, useEffect, useState } from 'react';
import { api, resolveMediaUrl } from '../../shared/api';
import type {
  Category,
  Product,
  ProductStatus,
  ProductVariantPayload,
  Tag,
} from '../../shared/api';
import { ErrorState, LoadingState } from '../../shared/ui/DataState';
import { ImageCropEditor, PRODUCT_IMAGE_CROP_SPEC } from '../../shared/ui/ImageCropEditor';
import { StatusBadge } from '../../shared/ui/StatusBadge';
import { formatDate, formatMoney, slugify } from '../../shared/utils/format';

interface PageProps {
  mode: 'create' | 'edit';
  productId?: number;
  onNavigate: (path: string) => void;
  onAuthExpired: () => void;
}

interface ProductFormState {
  name: string;
  slug: string;
  description: string;
  basePrice: string;
  status: ProductStatus;
  categoryId: string;
  tagIds: number[];
}

interface VariantRow {
  localId: number;
  id?: number;
  size: string;
  color: string;
  sku: string;
  stockQuantity: string;
  reservedQuantity: string;
  isActive: boolean;
  remove?: boolean;
}

const initialForm: ProductFormState = {
  name: '',
  slug: '',
  description: '',
  basePrice: '',
  status: 'DRAFT',
  categoryId: '',
  tagIds: [],
};

function createVariantRow(): VariantRow {
  return {
    localId: Date.now() + Math.random(),
    size: '',
    color: '',
    sku: '',
    stockQuantity: '0',
    reservedQuantity: '0',
    isActive: true,
  };
}

export function ProductEditorPage({ mode, productId, onNavigate, onAuthExpired }: PageProps) {
  const [form, setForm] = useState<ProductFormState>(initialForm);
  const [variants, setVariants] = useState<VariantRow[]>([createVariantRow()]);
  const [categories, setCategories] = useState<Category[]>([]);
  const [tags, setTags] = useState<Tag[]>([]);
  const [product, setProduct] = useState<Product | null>(null);
  const [imageFiles, setImageFiles] = useState<File[]>([]);
  const [pendingCropFiles, setPendingCropFiles] = useState<File[]>([]);
  const [loading, setLoading] = useState(mode === 'edit');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [createdProductId, setCreatedProductId] = useState<number | null>(null);

  function loadFormData() {
    setLoading(true);
    setError(null);

    Promise.all([
      api.categories.list(),
      api.tags.list(),
      mode === 'edit' && productId ? api.products.getAdmin(productId) : Promise.resolve(null),
    ])
      .then(([categoryList, tagList, loadedProduct]) => {
        setCategories(categoryList);
        setTags(tagList);

        if (loadedProduct) {
          setProduct(loadedProduct);
          setForm({
            name: loadedProduct.name,
            slug: loadedProduct.slug,
            description: loadedProduct.description ?? '',
            basePrice: String(loadedProduct.base_price),
            status: loadedProduct.status,
            categoryId: loadedProduct.category_id ? String(loadedProduct.category_id) : '',
            tagIds: loadedProduct.tags.map((tag) => tag.id),
          });
          setVariants(
            loadedProduct.variants.length > 0
              ? loadedProduct.variants.map((variant) => ({
                  localId: variant.id,
                  id: variant.id,
                  size: variant.size,
                  color: variant.color ?? '',
                  sku: variant.sku,
                  stockQuantity: String(variant.stock_quantity),
                  reservedQuantity: String(variant.reserved_quantity),
                  isActive: variant.is_active,
                }))
              : [createVariantRow()],
          );
        }
      })
      .catch(setError)
      .finally(() => setLoading(false));
  }

  useEffect(() => {
    loadFormData();
  }, [mode, productId]);

  function updateField<Key extends keyof ProductFormState>(key: Key, value: ProductFormState[Key]) {
    setForm((current) => ({ ...current, [key]: value }));
  }

  function handleImageSelection(event: ChangeEvent<HTMLInputElement>) {
    const selectedFiles = Array.from(event.target.files ?? []);
    if (selectedFiles.length > 0) {
      setPendingCropFiles((current) => [...current, ...selectedFiles]);
    }
    event.target.value = '';
  }

  function handleProductCropApply(file: File) {
    setImageFiles((current) => [...current, file]);
    setPendingCropFiles((current) => current.slice(1));
  }

  function handleProductCropCancel() {
    setPendingCropFiles((current) => current.slice(1));
  }

  function removePreparedImage(index: number) {
    setImageFiles((current) => current.filter((_, currentIndex) => currentIndex !== index));
  }

  function toggleTag(tagId: number) {
    setForm((current) => ({
      ...current,
      tagIds: current.tagIds.includes(tagId)
        ? current.tagIds.filter((currentTagId) => currentTagId !== tagId)
        : [...current.tagIds, tagId],
    }));
  }

  function updateVariant(localId: number, patch: Partial<VariantRow>) {
    setVariants((current) =>
      current.map((variant) => (variant.localId === localId ? { ...variant, ...patch } : variant)),
    );
  }

  function removeVariant(row: VariantRow) {
    setVariants((current) => {
      if (row.id) {
        return current.map((variant) =>
          variant.localId === row.localId ? { ...variant, remove: true } : variant,
        );
      }

      const next = current.filter((variant) => variant.localId !== row.localId);
      return next.length > 0 ? next : [createVariantRow()];
    });
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSaving(true);
    setError(null);
    setFormError(null);
    setSuccess(null);

    if (!form.name.trim() || !form.slug.trim() || !form.basePrice.trim()) {
      setFormError('Name, slug, and base price are required.');
      setSaving(false);
      return;
    }

    try {
      const payload = {
        name: form.name.trim(),
        slug: form.slug.trim(),
        description: form.description.trim() || null,
        base_price: form.basePrice.trim(),
        status: form.status,
        category_id: form.categoryId ? Number(form.categoryId) : null,
        tag_ids: form.tagIds,
      };

      const savedProduct =
        mode === 'edit' && productId
          ? await api.products.update(productId, payload)
          : await api.products.create({ ...payload, images: [] });

      await persistImages(savedProduct);
      await persistVariants(savedProduct.id);

      setCreatedProductId(savedProduct.id);
      setSuccess(`Product ${savedProduct.name} saved.`);
      setImageFiles([]);

      if (mode === 'edit') {
        loadFormData();
      }
    } catch (requestError) {
      setError(requestError);
    } finally {
      setSaving(false);
    }
  }

  async function persistImages(savedProduct: Product) {
    for (let index = 0; index < imageFiles.length; index += 1) {
      await api.products.uploadImage(savedProduct.id, imageFiles[index], {
        position: savedProduct.images.length + index,
        isPrimary: savedProduct.images.length === 0 && index === 0,
      });
    }
  }

  async function persistVariants(savedProductId: number) {
    for (const row of variants) {
      if (row.remove && row.id) {
        await api.products.deleteVariant(row.id);
        continue;
      }

      if (row.remove || (!row.size.trim() && !row.sku.trim())) {
        continue;
      }

      if (!row.size.trim() || !row.sku.trim()) {
        throw new Error('Each variant needs at least size and SKU.');
      }

      const payload: ProductVariantPayload = {
        size: row.size.trim(),
        color: row.color.trim() || null,
        sku: row.sku.trim(),
        stock_quantity: Number(row.stockQuantity || 0),
        reserved_quantity: Number(row.reservedQuantity || 0),
        is_active: row.isActive,
      };

      if (row.id) {
        await api.products.updateVariant(row.id, payload);
      } else {
        await api.products.createVariant(savedProductId, payload);
      }
    }
  }

  if (loading) return <LoadingState title="Loading product form" />;
  if (error) {
    return <ErrorState error={error} onRetry={loadFormData} onAuthExpired={onAuthExpired} />;
  }

  const visibleVariants = variants.filter((variant) => !variant.remove);
  const activeCropFile = pendingCropFiles[0] ?? null;

  return (
    <form className="page-stack" onSubmit={handleSubmit}>
      {formError ? <div className="form-error">{formError}</div> : null}
      {success ? (
        <div className="success-banner">
          {success}{' '}
          {mode === 'create' && createdProductId ? (
            <button
              className="text-button"
              type="button"
              onClick={() => onNavigate(`/products/${createdProductId}/edit`)}
            >
              Open edit page
            </button>
          ) : null}
        </div>
      ) : null}

      <div className="form-layout">
        <section className="panel">
          <div className="section-heading">
            <h2>Basic information</h2>
            {product ? <StatusBadge status={product.status} /> : null}
          </div>
          <div className="form-grid">
            <label className="field">
              <span>Name</span>
              <input
                value={form.name}
                onChange={(event) => {
                  updateField('name', event.target.value);
                  if (!form.slug || form.slug === slugify(form.name)) {
                    updateField('slug', slugify(event.target.value));
                  }
                }}
              />
            </label>
            <label className="field">
              <span>Slug</span>
              <input value={form.slug} onChange={(event) => updateField('slug', event.target.value)} />
            </label>
            <label className="field">
              <span>Base price</span>
              <input
                min="0"
                step="0.01"
                type="number"
                value={form.basePrice}
                onChange={(event) => updateField('basePrice', event.target.value)}
              />
            </label>
            <label className="field">
              <span>Status</span>
              <select
                value={form.status}
                onChange={(event) => updateField('status', event.target.value as ProductStatus)}
              >
                <option value="DRAFT">Draft</option>
                <option value="ACTIVE">Active</option>
                <option value="OUT_OF_STOCK">Out of stock</option>
                <option value="ARCHIVED">Archived</option>
              </select>
            </label>
            <label className="field field-wide">
              <span>Description</span>
              <textarea
                rows={5}
                value={form.description}
                onChange={(event) => updateField('description', event.target.value)}
              />
            </label>
          </div>
        </section>

        <aside className="panel compact-panel">
          <h2>Current state</h2>
          {product ? (
            <dl className="details-list">
              <div>
                <dt>ID</dt>
                <dd>{product.id}</dd>
              </div>
              <div>
                <dt>Created</dt>
                <dd>{formatDate(product.created_at)}</dd>
              </div>
              <div>
                <dt>Updated</dt>
                <dd>{formatDate(product.updated_at)}</dd>
              </div>
              <div>
                <dt>Price</dt>
                <dd>{formatMoney(product.base_price)}</dd>
              </div>
            </dl>
          ) : (
            <p className="muted-text">A new product will be created as a draft unless published.</p>
          )}
        </aside>
      </div>

      <section className="panel">
        <h2>Category and tags</h2>
        <div className="form-grid">
          <label className="field">
            <span>Category</span>
            <select
              value={form.categoryId}
              onChange={(event) => updateField('categoryId', event.target.value)}
            >
              <option value="">Unassigned</option>
              {categories.map((category) => (
                <option key={category.id} value={category.id}>
                  {category.name}
                </option>
              ))}
            </select>
          </label>
          <div className="field field-wide">
            <span>Tags</span>
            <div className="checkbox-grid">
              {tags.map((tag) => (
                <label key={tag.id}>
                  <input
                    checked={form.tagIds.includes(tag.id)}
                    type="checkbox"
                    onChange={() => toggleTag(tag.id)}
                  />
                  {tag.name}
                </label>
              ))}
              {tags.length === 0 ? <span className="muted-text">No tags available.</span> : null}
            </div>
          </div>
        </div>
      </section>

      <section className="panel">
        <h2>Images</h2>
        {product && product.images.length > 0 ? (
          <div className="image-strip">
            {product.images.map((image) => (
              <img
                key={image.id}
                src={resolveMediaUrl(image.url)}
                alt={image.alt_text ?? product.name}
              />
            ))}
          </div>
        ) : (
          <p className="muted-text">No product images uploaded yet.</p>
        )}
        <label className="field">
          <span>Upload images</span>
          <p className="image-hints">
            Рекомендуемый размер: {PRODUCT_IMAGE_CROP_SPEC.outputWidth}x
            {PRODUCT_IMAGE_CROP_SPEC.outputHeight}. Минимальный размер:{' '}
            {PRODUCT_IMAGE_CROP_SPEC.minWidth}x{PRODUCT_IMAGE_CROP_SPEC.minHeight}.
          </p>
          <input accept="image/*" multiple type="file" onChange={handleImageSelection} />
        </label>
        {imageFiles.length > 0 ? (
          <div className="upload-list">
            {imageFiles.map((file, index) => (
              <span key={`${file.name}-${index}`}>
                {file.name}
                <button
                  className="text-button danger-text"
                  type="button"
                  onClick={() => removePreparedImage(index)}
                >
                  Remove
                </button>
              </span>
            ))}
          </div>
        ) : null}
      </section>

      <section className="panel">
        <div className="section-heading">
          <h2>Variants and stock</h2>
          <button className="button button-secondary" type="button" onClick={() => setVariants((current) => [...current, createVariantRow()])}>
            Add variant
          </button>
        </div>
        <div className="variant-grid">
          {visibleVariants.map((variant) => (
            <div className="variant-row" key={variant.localId}>
              <label>
                <span>Size</span>
                <input
                  value={variant.size}
                  onChange={(event) => updateVariant(variant.localId, { size: event.target.value })}
                />
              </label>
              <label>
                <span>Color</span>
                <input
                  value={variant.color}
                  onChange={(event) => updateVariant(variant.localId, { color: event.target.value })}
                />
              </label>
              <label>
                <span>SKU</span>
                <input
                  value={variant.sku}
                  onChange={(event) => updateVariant(variant.localId, { sku: event.target.value })}
                />
              </label>
              <label>
                <span>Stock</span>
                <input
                  min="0"
                  type="number"
                  value={variant.stockQuantity}
                  onChange={(event) =>
                    updateVariant(variant.localId, { stockQuantity: event.target.value })
                  }
                />
              </label>
              <label>
                <span>Reserved</span>
                <input
                  min="0"
                  type="number"
                  value={variant.reservedQuantity}
                  onChange={(event) =>
                    updateVariant(variant.localId, { reservedQuantity: event.target.value })
                  }
                />
              </label>
              <label className="toggle-label">
                <input
                  checked={variant.isActive}
                  type="checkbox"
                  onChange={(event) =>
                    updateVariant(variant.localId, { isActive: event.target.checked })
                  }
                />
                Active
              </label>
              <button
                className="text-button danger-text"
                type="button"
                onClick={() => removeVariant(variant)}
              >
                Remove
              </button>
            </div>
          ))}
        </div>
      </section>

      <div className="form-actions">
        <button className="button button-secondary" type="button" onClick={() => onNavigate('/products')}>
          Back to products
        </button>
        <button className="button button-primary" disabled={saving} type="submit">
          {saving ? 'Saving...' : mode === 'create' ? 'Create product' : 'Save changes'}
        </button>
      </div>
      {activeCropFile ? (
        <ImageCropEditor
          file={activeCropFile}
          spec={PRODUCT_IMAGE_CROP_SPEC}
          onApply={handleProductCropApply}
          onCancel={handleProductCropCancel}
        />
      ) : null}
    </form>
  );
}
