import { ChangeEvent, FormEvent, useEffect, useState } from 'react';
import { api, resolveMediaUrl } from '../../shared/api';
import type {
  Category,
  Product,
  ProductImageBadgeColor,
  ProductImageBadgePosition,
  ProductImageBadgeType,
  ProductSizeGrid,
  ProductStatus,
  ProductVariantPayload,
  Tag,
} from '../../shared/api';
import { labelForEnum, useI18n } from '../../shared/i18n';
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
  brand: string;
  description: string;
  basePrice: string;
  oldPrice: string;
  searchPriority: string;
  searchAliases: string;
  sizeGrid: ProductSizeGrid;
  imageBadgeType: ProductImageBadgeType;
  imageBadgeText: string;
  imageBadgeColor: ProductImageBadgeColor;
  imageBadgePosition: ProductImageBadgePosition;
  status: ProductStatus;
  tagIds: number[];
}

interface CategoryAssignmentRow {
  localId: number;
  categoryId: string;
  priority: '1' | '2' | '3';
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
  brand: '',
  description: '',
  basePrice: '',
  oldPrice: '',
  searchPriority: '2',
  searchAliases: '',
  sizeGrid: 'clothing_alpha',
  imageBadgeType: 'none',
  imageBadgeText: '',
  imageBadgeColor: 'purple',
  imageBadgePosition: 'top-left',
  status: 'DRAFT',
  tagIds: [],
};

const CLOTHING_SIZES = ['XS', 'S', 'M', 'L', 'XL', 'XXL', '3XL', 'ONE_SIZE'] as const;
const SHOE_SIZES_EU = ['35', '36', '37', '38', '39', '40', '41', '42', '43', '44', '45', '46'] as const;
const SHOE_SIZES_RU = SHOE_SIZES_EU;
const BADGE_COLORS: Array<{ value: ProductImageBadgeColor; labelKey: string }> = [
  { value: 'purple', labelKey: 'productEditor.badgeColorPurple' },
  { value: 'pink', labelKey: 'productEditor.badgeColorPink' },
  { value: 'red', labelKey: 'productEditor.badgeColorRed' },
  { value: 'orange', labelKey: 'productEditor.badgeColorOrange' },
  { value: 'blue', labelKey: 'productEditor.badgeColorBlue' },
  { value: 'green', labelKey: 'productEditor.badgeColorGreen' },
  { value: 'black', labelKey: 'productEditor.badgeColorBlack' },
  { value: 'white', labelKey: 'productEditor.badgeColorWhite' },
];
const BADGE_POSITIONS: Array<{ value: ProductImageBadgePosition; labelKey: string }> = [
  { value: 'top-left', labelKey: 'productEditor.badgePositionTopLeft' },
  { value: 'top-right', labelKey: 'productEditor.badgePositionTopRight' },
  { value: 'bottom-left', labelKey: 'productEditor.badgePositionBottomLeft' },
  { value: 'bottom-right', labelKey: 'productEditor.badgePositionBottomRight' },
];

function allowedSizes(sizeGrid: ProductSizeGrid): readonly string[] {
  if (sizeGrid === 'shoes_eu') return SHOE_SIZES_EU;
  if (sizeGrid === 'shoes_ru') return SHOE_SIZES_RU;
  return CLOTHING_SIZES;
}

function createCategoryAssignmentRow(priority: '1' | '2' | '3' = '1'): CategoryAssignmentRow {
  return {
    localId: Date.now() + Math.random(),
    categoryId: '',
    priority,
  };
}

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
  const { language, t } = useI18n();
  const [form, setForm] = useState<ProductFormState>(initialForm);
  const [categoryAssignments, setCategoryAssignments] = useState<CategoryAssignmentRow[]>([
    createCategoryAssignmentRow(),
  ]);
  const [variants, setVariants] = useState<VariantRow[]>([createVariantRow()]);
  const [categories, setCategories] = useState<Category[]>([]);
  const [tags, setTags] = useState<Tag[]>([]);
  const [availableProducts, setAvailableProducts] = useState<Product[]>([]);
  const [relatedProductIds, setRelatedProductIds] = useState<string[]>([]);
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
      api.products.listAdmin({ limit: 100, offset: 0 }),
      mode === 'edit' && productId ? api.products.getAdmin(productId) : Promise.resolve(null),
    ])
      .then(([categoryList, tagList, productList, loadedProduct]) => {
        setCategories(categoryList);
        setTags(tagList);
        setAvailableProducts(productList.items);

        if (loadedProduct) {
          setProduct(loadedProduct);
          setForm({
            name: loadedProduct.name,
            slug: loadedProduct.slug,
            brand: loadedProduct.brand ?? '',
            description: loadedProduct.description ?? '',
            basePrice: String(loadedProduct.base_price),
            oldPrice: loadedProduct.old_price ? String(loadedProduct.old_price) : '',
            searchPriority: String(loadedProduct.search_priority ?? 2),
            searchAliases: loadedProduct.search_aliases ?? '',
            sizeGrid: loadedProduct.size_grid ?? 'clothing_alpha',
            imageBadgeType: loadedProduct.image_badge_type ?? 'none',
            imageBadgeText: loadedProduct.image_badge_text ?? '',
            imageBadgeColor:
              loadedProduct.image_badge_color ??
              getDefaultBadgeColor(loadedProduct.image_badge_type ?? 'none'),
            imageBadgePosition:
              loadedProduct.image_badge_position ??
              getDefaultBadgePosition(loadedProduct.image_badge_type ?? 'none'),
            status: loadedProduct.status,
            tagIds: loadedProduct.tags.map((tag) => tag.id),
          });
          setCategoryAssignments(getCategoryRowsFromProduct(loadedProduct));
          setRelatedProductIds(
            (loadedProduct.related_product_ids ?? []).map((relatedId) => String(relatedId)),
          );
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
        } else {
          setCategoryAssignments([createCategoryAssignmentRow()]);
          setRelatedProductIds([]);
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

  function changeBadgeType(nextType: ProductImageBadgeType) {
    setForm((current) => {
      const currentDefaultColor = getDefaultBadgeColor(current.imageBadgeType);
      const currentDefaultPosition = getDefaultBadgePosition(current.imageBadgeType);

      return {
        ...current,
        imageBadgeType: nextType,
        imageBadgeColor:
          current.imageBadgeColor === currentDefaultColor
            ? getDefaultBadgeColor(nextType)
            : current.imageBadgeColor,
        imageBadgePosition:
          current.imageBadgePosition === currentDefaultPosition
            ? getDefaultBadgePosition(nextType)
            : current.imageBadgePosition,
      };
    });
  }

  function changeSizeGrid(nextGrid: ProductSizeGrid) {
    if (
      form.sizeGrid === 'shoes_ru' &&
      nextGrid === 'shoes_eu' &&
      variants.some((variant) => !variant.remove && variant.size.trim())
    ) {
      setFormError(t('productEditor.legacyRuToEuBlocked'));
      return;
    }
    const persistedIncompatible = variants
      .filter((variant) => variant.id && variant.size.trim())
      .map((variant) => variant.size.trim())
      .filter((size) => !allowedSizes(nextGrid).includes(size));
    if (persistedIncompatible.length > 0) {
      setFormError(
        t('productEditor.persistedIncompatibleSizes', {
          sizes: Array.from(new Set(persistedIncompatible)).join(', '),
        }),
      );
      return;
    }
    const incompatible = variants
      .filter((variant) => !variant.remove && variant.size.trim())
      .map((variant) => variant.size.trim())
      .filter((size) => !allowedSizes(nextGrid).includes(size));
    if (incompatible.length > 0) {
      setFormError(
        t('productEditor.incompatibleSizes', {
          sizes: Array.from(new Set(incompatible)).join(', '),
        }),
      );
      return;
    }
    setFormError(null);
    updateField('sizeGrid', nextGrid);
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

  function updateCategoryAssignment(localId: number, patch: Partial<CategoryAssignmentRow>) {
    setCategoryAssignments((current) =>
      current.map((assignment) =>
        assignment.localId === localId ? { ...assignment, ...patch } : assignment,
      ),
    );
  }

  function addCategoryAssignment() {
    setCategoryAssignments((current) => {
      if (current.length >= 3) {
        return current;
      }
      const usedPriorities = new Set(current.map((assignment) => assignment.priority));
      const nextPriority =
        (['1', '2', '3'] as const).find((priority) => !usedPriorities.has(priority)) ?? '3';
      return [...current, createCategoryAssignmentRow(nextPriority)];
    });
  }

  function removeCategoryAssignment(localId: number) {
    setCategoryAssignments((current) => {
      const next = current.filter((assignment) => assignment.localId !== localId);
      return next.length > 0 ? next : [createCategoryAssignmentRow()];
    });
  }

  function addRelatedProduct() {
    setRelatedProductIds((current) => [...current, '']);
  }

  function updateRelatedProduct(index: number, value: string) {
    setRelatedProductIds((current) =>
      current.map((relatedId, currentIndex) => currentIndex === index ? value : relatedId),
    );
  }

  function removeRelatedProduct(index: number) {
    setRelatedProductIds((current) => current.filter((_, currentIndex) => currentIndex !== index));
  }

  function moveRelatedProduct(index: number, direction: -1 | 1) {
    setRelatedProductIds((current) => {
      const targetIndex = index + direction;
      if (targetIndex < 0 || targetIndex >= current.length) return current;
      const next = [...current];
      [next[index], next[targetIndex]] = [next[targetIndex], next[index]];
      return next;
    });
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
      setFormError(t('productEditor.required'));
      setSaving(false);
      return;
    }

    if (form.oldPrice.trim() && Number(form.oldPrice) <= Number(form.basePrice)) {
      setFormError(t('productEditor.oldPriceInvalid'));
      setSaving(false);
      return;
    }

    const normalizedCategories = normalizeCategoryAssignments(categoryAssignments);
    if (normalizedCategories.length > 3) {
      setFormError(t('productEditor.maxCategories'));
      setSaving(false);
      return;
    }

    if (hasDuplicateValues(normalizedCategories.map((assignment) => assignment.category_id))) {
      setFormError(t('productEditor.duplicateCategories'));
      setSaving(false);
      return;
    }

    if (hasDuplicateValues(normalizedCategories.map((assignment) => assignment.priority))) {
      setFormError(t('productEditor.duplicateCategoryPriorities'));
      setSaving(false);
      return;
    }

    const normalizedRelatedProductIds = relatedProductIds
      .map((relatedId) => Number(relatedId))
      .filter((relatedId) => Number.isInteger(relatedId) && relatedId > 0);
    if (normalizedRelatedProductIds.length !== relatedProductIds.filter(Boolean).length) {
      setFormError(t('productEditor.relatedInvalid'));
      setSaving(false);
      return;
    }
    if (hasDuplicateValues(normalizedRelatedProductIds)) {
      setFormError(t('productEditor.relatedDuplicate'));
      setSaving(false);
      return;
    }
    if (productId && normalizedRelatedProductIds.includes(productId)) {
      setFormError(t('productEditor.relatedSelf'));
      setSaving(false);
      return;
    }
    if (form.imageBadgeType === 'custom' && !form.imageBadgeText.trim()) {
      setFormError(t('productEditor.badgeCustomRequired'));
      setSaving(false);
      return;
    }

    const variantKeys = variants
      .filter((variant) => !variant.remove && variant.size.trim())
      .map((variant) => `${variant.size.trim()}::${normalizeVariantColorKey(variant.color)}`);
    if (hasDuplicateValues(variantKeys)) {
      setFormError(t('productEditor.duplicateVariants'));
      setSaving(false);
      return;
    }

    const primaryCategoryId =
      [...normalizedCategories].sort((left, right) => left.priority - right.priority)[0]
        ?.category_id ?? null;

    try {
      const payload = {
        name: form.name.trim(),
        slug: form.slug.trim(),
        brand: form.brand.trim() || null,
        description: form.description.trim() || null,
        base_price: form.basePrice.trim(),
        old_price: form.oldPrice.trim() || null,
        search_priority: parseSearchPriority(form.searchPriority),
        search_aliases: normalizeSearchAliases(form.searchAliases),
        size_grid: form.sizeGrid,
        image_badge_type: form.imageBadgeType,
        image_badge_text: form.imageBadgeType === 'custom' ? form.imageBadgeText.trim() : null,
        image_badge_color: form.imageBadgeColor,
        image_badge_position: form.imageBadgePosition,
        status: form.status,
        category_id: primaryCategoryId,
        categories: normalizedCategories,
        tag_ids: form.tagIds,
        related_product_ids: normalizedRelatedProductIds,
      };

      const savedProduct =
        mode === 'edit' && productId
          ? await api.products.update(productId, payload)
          : await api.products.create({ ...payload, images: [] });

      await persistImages(savedProduct);
      await persistVariants(savedProduct.id);

      setCreatedProductId(savedProduct.id);
      setSuccess(t('productEditor.saved', { name: savedProduct.name }));
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
        throw new Error(t('productEditor.variantRequired'));
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

  if (loading) return <LoadingState title={t('productEditor.loading')} />;
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
              {t('productEditor.openEdit')}
            </button>
          ) : null}
        </div>
      ) : null}

      <div className="form-layout">
        <section className="panel">
          <div className="section-heading">
            <h2>{t('productEditor.basicInfo')}</h2>
            {product ? <StatusBadge status={product.status} /> : null}
          </div>
          <div className="form-grid">
            <label className="field">
              <span>{t('common.name')}</span>
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
              <span>{t('productEditor.slug')}</span>
              <input value={form.slug} onChange={(event) => updateField('slug', event.target.value)} />
            </label>
            <label className="field field-wide">
              <span>{t('productEditor.brand')}</span>
              <input
                maxLength={120}
                value={form.brand}
                onChange={(event) => updateField('brand', event.target.value)}
              />
              <small className="field-hint">{t('productEditor.brandHint')}</small>
            </label>
            <div className="form-pair-row field-wide">
              <label className="field">
                <span>{t('productEditor.basePrice')}</span>
                <input
                  min="0"
                  step="0.01"
                  type="number"
                  value={form.basePrice}
                  onChange={(event) => updateField('basePrice', event.target.value)}
                />
              </label>
              <label className="field">
                <span>{t('productEditor.oldPrice')}</span>
                <input
                  min="0"
                  step="0.01"
                  type="number"
                  value={form.oldPrice}
                  onChange={(event) => updateField('oldPrice', event.target.value)}
                />
                <small className="field-hint">{t('productEditor.oldPriceHint')}</small>
              </label>
            </div>
            <div className="form-pair-row field-wide">
              <label className="field">
                <span>{t('common.status')}</span>
                <select
                  value={form.status}
                  onChange={(event) => updateField('status', event.target.value as ProductStatus)}
                >
                  <option value="DRAFT">{labelForEnum('DRAFT', t)}</option>
                  <option value="ACTIVE">{labelForEnum('ACTIVE', t)}</option>
                  <option value="OUT_OF_STOCK">{labelForEnum('OUT_OF_STOCK', t)}</option>
                  <option value="ARCHIVED">{labelForEnum('ARCHIVED', t)}</option>
                </select>
              </label>
              <label className="field">
                <span>{t('productEditor.searchPriority')}</span>
                <select
                  value={form.searchPriority}
                  onChange={(event) => updateField('searchPriority', event.target.value)}
                >
                  <option value="1">{t('productEditor.priorityHigh')}</option>
                  <option value="2">{t('productEditor.priorityMedium')}</option>
                  <option value="3">{t('productEditor.priorityLow')}</option>
                </select>
                <small className="field-hint">{t('productEditor.searchPriorityHint')}</small>
              </label>
            </div>
            <label className="field field-wide">
              <span>{t('common.description')}</span>
              <textarea
                rows={5}
                value={form.description}
                onChange={(event) => updateField('description', event.target.value)}
              />
            </label>
            <label className="field field-wide">
              <span>{t('productEditor.searchAliases')}</span>
              <textarea
                rows={4}
                value={form.searchAliases}
                onChange={(event) => updateField('searchAliases', event.target.value)}
              />
              <small className="field-hint">{t('productEditor.searchAliasesHint')}</small>
            </label>
          </div>
        </section>

        <aside className="panel compact-panel">
          <h2>{t('productEditor.currentState')}</h2>
          {product ? (
            <dl className="details-list">
              <div>
                <dt>ID</dt>
                <dd>{product.id}</dd>
              </div>
              <div>
                <dt>{t('common.created')}</dt>
                <dd>{formatDate(product.created_at, language)}</dd>
              </div>
              <div>
                <dt>{t('common.updated')}</dt>
                <dd>{formatDate(product.updated_at, language)}</dd>
              </div>
              <div>
                <dt>{t('products.price')}</dt>
                <dd>
                  <span className="price-stack">
                    {product.old_price ? (
                      <span className="old-price">{formatMoney(product.old_price, language)}</span>
                    ) : null}
                    <strong>{formatMoney(product.base_price, language)}</strong>
                  </span>
                </dd>
              </div>
              <div>
                <dt>{t('productEditor.searchPriority')}</dt>
                <dd>{product.search_priority ?? 2}</dd>
              </div>
            </dl>
          ) : (
            <p className="muted-text">{t('productEditor.newDraftHint')}</p>
          )}
        </aside>
      </div>

      <section className="panel">
        <h2>{t('productEditor.categoryTags')}</h2>
        <div className="form-grid">
          <div className="field field-wide">
            <span>{t('productEditor.categoryAssignments')}</span>
            <div className="category-assignment-list">
              {categoryAssignments.map((assignment) => (
                <div className="category-assignment-row" key={assignment.localId}>
                  <label>
                    <span>{t('common.category')}</span>
                    <select
                      value={assignment.categoryId}
                      onChange={(event) =>
                        updateCategoryAssignment(assignment.localId, {
                          categoryId: event.target.value,
                        })
                      }
                    >
                      <option value="">{t('products.unassigned')}</option>
                      {categories.map((category) => (
                        <option key={category.id} value={category.id}>
                          {category.name}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label>
                    <span>{t('productEditor.categoryPriority')}</span>
                    <select
                      value={assignment.priority}
                      onChange={(event) =>
                        updateCategoryAssignment(assignment.localId, {
                          priority: event.target.value as CategoryAssignmentRow['priority'],
                        })
                      }
                    >
                      <option value="1">{t('productEditor.priorityHigh')}</option>
                      <option value="2">{t('productEditor.priorityMedium')}</option>
                      <option value="3">{t('productEditor.priorityLow')}</option>
                    </select>
                  </label>
                  <button
                    className="text-button danger-text"
                    type="button"
                    onClick={() => removeCategoryAssignment(assignment.localId)}
                  >
                    {t('common.remove')}
                  </button>
                </div>
              ))}
            </div>
            <div className="category-assignment-actions">
              <button
                className="button button-secondary"
                disabled={categoryAssignments.length >= 3}
                type="button"
                onClick={addCategoryAssignment}
              >
                {t('productEditor.addCategory')}
              </button>
              <small className="field-hint">{t('productEditor.categoryPriorityHint')}</small>
            </div>
          </div>
          <div className="field field-wide">
            <span>{t('products.tags')}</span>
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
              {tags.length === 0 ? (
                <span className="muted-text">{t('productEditor.noTagsAvailable')}</span>
              ) : null}
            </div>
          </div>
        </div>
      </section>

      <section className="panel">
        <div className="section-heading">
          <div>
            <h2>{t('productEditor.relatedProducts')}</h2>
            <p className="muted-text">{t('productEditor.relatedProductsHint')}</p>
          </div>
          <button className="button button-secondary" type="button" onClick={addRelatedProduct}>
            {t('productEditor.addRelatedProduct')}
          </button>
        </div>
        <datalist id="related-product-options">
          {availableProducts
            .filter((candidate) => candidate.id !== productId)
            .map((candidate) => (
              <option key={candidate.id} value={candidate.id}>{candidate.name}</option>
            ))}
        </datalist>
        {relatedProductIds.length > 0 ? (
          <div className="related-product-list">
            {relatedProductIds.map((relatedId, index) => {
              const selectedProduct = availableProducts.find(
                (candidate) => candidate.id === Number(relatedId),
              );
              return (
                <div className="related-product-row" key={`${index}-${relatedId}`}>
                  <span className="related-product-position">{index + 1}</span>
                  <label className="field">
                    <span>{t('productEditor.relatedProductId')}</span>
                    <input
                      list="related-product-options"
                      min="1"
                      type="number"
                      value={relatedId}
                      onChange={(event) => updateRelatedProduct(index, event.target.value)}
                    />
                    <small className="field-hint">
                      {selectedProduct?.name ?? t('productEditor.relatedProductUnknown')}
                    </small>
                  </label>
                  <div className="related-product-actions">
                    <button
                      className="button button-secondary button-compact"
                      disabled={index === 0}
                      type="button"
                      onClick={() => moveRelatedProduct(index, -1)}
                      aria-label={t('productEditor.moveRelatedUp')}
                    >
                      ↑
                    </button>
                    <button
                      className="button button-secondary button-compact"
                      disabled={index === relatedProductIds.length - 1}
                      type="button"
                      onClick={() => moveRelatedProduct(index, 1)}
                      aria-label={t('productEditor.moveRelatedDown')}
                    >
                      ↓
                    </button>
                    <button
                      className="text-button danger-text"
                      type="button"
                      onClick={() => removeRelatedProduct(index)}
                    >
                      {t('common.remove')}
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        ) : (
          <p className="muted-text">{t('productEditor.noRelatedProducts')}</p>
        )}
      </section>

      <section className="panel">
        <h2>{t('productEditor.images')}</h2>
        <div className="badge-editor">
          <label className="field">
            <span>{t('productEditor.imageBadge')}</span>
            <select
              value={form.imageBadgeType}
              onChange={(event) =>
                changeBadgeType(event.target.value as ProductImageBadgeType)
              }
            >
              <option value="none">{t('productEditor.badgeNone')}</option>
              <option value="new">NEW</option>
              <option value="sale">{t('productEditor.badgeSale')}</option>
              <option value="hit">{t('productEditor.badgeHit')}</option>
              <option value="exclusive">{t('productEditor.badgeExclusive')}</option>
              <option value="custom">{t('productEditor.badgeCustom')}</option>
            </select>
          </label>
          {form.imageBadgeType === 'custom' ? (
            <label className="field">
              <span>{t('productEditor.badgeText')}</span>
              <input
                maxLength={20}
                value={form.imageBadgeText}
                onChange={(event) => updateField('imageBadgeText', event.target.value)}
              />
              <small className="field-hint">{form.imageBadgeText.length}/20</small>
            </label>
          ) : null}
          <label className="field">
            <span>{t('productEditor.badgeColor')}</span>
            <select
              value={form.imageBadgeColor}
              onChange={(event) =>
                updateField('imageBadgeColor', event.target.value as ProductImageBadgeColor)
              }
            >
              {BADGE_COLORS.map((color) => (
                <option key={color.value} value={color.value}>
                  {t(color.labelKey)}
                </option>
              ))}
            </select>
          </label>
          <label className="field">
            <span>{t('productEditor.badgePosition')}</span>
            <select
              value={form.imageBadgePosition}
              onChange={(event) =>
                updateField('imageBadgePosition', event.target.value as ProductImageBadgePosition)
              }
            >
              {BADGE_POSITIONS.map((position) => (
                <option key={position.value} value={position.value}>
                  {t(position.labelKey)}
                </option>
              ))}
            </select>
          </label>
          {form.imageBadgeType !== 'none' ? (
            <div className="image-badge-preview-frame" aria-label={t('productEditor.badgePreview')}>
              <div
                className={`image-badge-preview image-badge-preview--color-${form.imageBadgeColor} image-badge-preview--position-${form.imageBadgePosition}`}
              >
                {getBadgePreviewText(form.imageBadgeType, form.imageBadgeText, t)}
              </div>
            </div>
          ) : null}
        </div>
        {product && product.images.length > 0 ? (
          <div className="image-strip">
            {product.images.map((image) => (
              <img
                key={image.id}
                src={resolveMediaUrl(image.thumbnail_url ?? image.card_url ?? image.url)}
                alt={image.alt_text ?? product.name}
                width={96}
                height={120}
                loading="lazy"
                decoding="async"
              />
            ))}
          </div>
        ) : (
          <p className="muted-text">{t('productEditor.noImages')}</p>
        )}
        <label className="field">
          <span>{t('productEditor.uploadImages')}</span>
          <p className="image-hints image-hints-current">
            {t('productEditor.imageHint', {
              width: PRODUCT_IMAGE_CROP_SPEC.outputWidth,
              height: PRODUCT_IMAGE_CROP_SPEC.outputHeight,
              minWidth: PRODUCT_IMAGE_CROP_SPEC.minWidth,
              minHeight: PRODUCT_IMAGE_CROP_SPEC.minHeight,
            })}
          </p>
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
                  {t('common.remove')}
                </button>
              </span>
            ))}
          </div>
        ) : null}
      </section>

      <section className="panel">
        <div className="section-heading">
          <h2>{t('productEditor.variantsStock')}</h2>
          <button className="button button-secondary" type="button" onClick={() => setVariants((current) => [...current, createVariantRow()])}>
            {t('productEditor.addVariant')}
          </button>
        </div>
        <label className="field field-wide">
          <span>{t('productEditor.sizeGrid')}</span>
          <select
            value={form.sizeGrid}
            onChange={(event) => changeSizeGrid(event.target.value as ProductSizeGrid)}
          >
            <option value="clothing_alpha">{t('productEditor.sizeGridClothing')}</option>
            <option value="shoes_eu">{t('productEditor.sizeGridShoesEu')}</option>
            {form.sizeGrid === 'shoes_ru' ? (
              <option value="shoes_ru">{t('productEditor.sizeGridShoesRuLegacy')}</option>
            ) : null}
          </select>
        </label>
        <div className="variant-grid">
          {visibleVariants.map((variant) => (
            <div className="variant-row" key={variant.localId}>
              <label>
                <span>{t('productEditor.size')}</span>
                <select
                  value={variant.size}
                  onChange={(event) => updateVariant(variant.localId, { size: event.target.value })}
                >
                  <option value="">{t('productEditor.selectSize')}</option>
                  {variant.size && !allowedSizes(form.sizeGrid).includes(variant.size) ? (
                    <option value={variant.size} disabled>{variant.size}</option>
                  ) : null}
                  {allowedSizes(form.sizeGrid).map((size) => (
                    <option value={size} key={size}>
                      {size === 'ONE_SIZE' ? t('productEditor.oneSize') : size}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                <span>{t('productEditor.color')}</span>
                <input
                  autoComplete="off"
                  value={variant.color}
                  onChange={(event) => updateVariant(variant.localId, { color: event.target.value })}
                />
                <small className="field-hint">{t('productEditor.colorHint')}</small>
              </label>
              <label>
                <span>{t('productEditor.sku')}</span>
                <input
                  value={variant.sku}
                  onChange={(event) => updateVariant(variant.localId, { sku: event.target.value })}
                />
              </label>
              <label>
                <span>{t('productEditor.stock')}</span>
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
                <span>{t('productEditor.reserved')}</span>
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
                {t('common.active')}
              </label>
              <button
                className="text-button danger-text"
                type="button"
                onClick={() => removeVariant(variant)}
              >
                {t('common.remove')}
              </button>
              <div className="variant-summary">
                <strong>{variant.size === 'ONE_SIZE' ? t('productEditor.oneSize') : variant.size || '—'}</strong>
                <span>{variant.color || t('common.notProvided')}</span>
                <span>{Math.max(0, Number(variant.stockQuantity || 0) - Number(variant.reservedQuantity || 0))}/{Number(variant.stockQuantity || 0)} {t('productEditor.stock')}</span>
                <span>{variant.sku || 'SKU —'}</span>
                <span>{variant.isActive ? t('common.active') : t('common.inactive')}</span>
              </div>
            </div>
          ))}
        </div>
      </section>

      <div className="form-actions">
        <button className="button button-secondary" type="button" onClick={() => onNavigate('/products')}>
          {t('productEditor.backToProducts')}
        </button>
        <button className="button button-primary" disabled={saving} type="submit">
          {saving
            ? t('common.saving')
            : mode === 'create'
              ? t('productEditor.createProduct')
              : t('productEditor.saveChanges')}
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

function getBadgePreviewText(
  badgeType: ProductImageBadgeType,
  customText: string,
  t: ReturnType<typeof useI18n>['t'],
) {
  if (badgeType === 'new') return 'NEW';
  if (badgeType === 'sale') return t('productEditor.badgeSale');
  if (badgeType === 'hit') return t('productEditor.badgeHit');
  if (badgeType === 'exclusive') return t('productEditor.badgeExclusive');
  return customText.trim() || t('productEditor.badgeCustom');
}

function getDefaultBadgeColor(badgeType: ProductImageBadgeType): ProductImageBadgeColor {
  if (badgeType === 'sale') return 'red';
  if (badgeType === 'hit') return 'orange';
  return 'purple';
}

function normalizeVariantColorKey(color: string) {
  return color.trim().toLocaleLowerCase('ru-RU');
}

function getDefaultBadgePosition(badgeType: ProductImageBadgeType): ProductImageBadgePosition {
  return badgeType === 'new' ? 'top-left' : 'bottom-left';
}

function getCategoryRowsFromProduct(product: Product): CategoryAssignmentRow[] {
  const rows =
    product.categories?.length > 0
      ? product.categories
          .slice()
          .sort((left, right) => left.priority - right.priority)
          .map((assignment) => ({
            localId: Date.now() + Math.random(),
            categoryId: String(assignment.category_id),
            priority: String(assignment.priority) as CategoryAssignmentRow['priority'],
          }))
      : product.category_id
        ? [
            {
              localId: Date.now() + Math.random(),
              categoryId: String(product.category_id),
              priority: '1' as const,
            },
          ]
        : [];

  return rows.length > 0 ? rows : [createCategoryAssignmentRow()];
}

function normalizeCategoryAssignments(assignments: CategoryAssignmentRow[]) {
  return assignments
    .filter((assignment) => assignment.categoryId)
    .map((assignment) => ({
      category_id: Number(assignment.categoryId),
      priority: Number(assignment.priority) as 1 | 2 | 3,
    }));
}

function hasDuplicateValues(values: Array<number | string>) {
  return new Set(values).size !== values.length;
}

function parseSearchPriority(value: string): 1 | 2 | 3 {
  if (value === '1') return 1;
  if (value === '3') return 3;
  return 2;
}

function normalizeSearchAliases(value: string): string | null {
  const aliases = value
    .replace(/,/g, '\n')
    .split('\n')
    .map((item) => item.trim())
    .filter(Boolean);
  if (aliases.length === 0) {
    return null;
  }
  return Array.from(new Set(aliases)).join('\n');
}
