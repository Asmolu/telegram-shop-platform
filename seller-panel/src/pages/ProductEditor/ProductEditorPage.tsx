import { ChangeEvent, FormEvent, useEffect, useMemo, useRef, useState } from 'react';
import { ApiError, api, resolveMediaUrl } from '../../shared/api';
import type {
  Category,
  Product,
  ProductImageBadgeColor,
  ProductImageBadgePosition,
  ProductImageBadgeType,
  ProductSizeGrid,
  ProductSizeGroup,
  ProductStatus,
  ProductVariant,
  Tag,
} from '../../shared/api';
import { labelForEnum, useI18n } from '../../shared/i18n';
import { ErrorState, LoadingState } from '../../shared/ui/DataState';
import { ImageCropEditor, PRODUCT_IMAGE_CROP_SPEC } from '../../shared/ui/ImageCropEditor';
import {
  ImageBadgeConfigurator,
  getDefaultImageBadgeColor,
  getDefaultImageBadgePosition,
  isImageBadgeConfigurationValid,
  normalizeImageBadgeText,
} from '../../shared/ui/ImageBadgeConfigurator';
import { StatusBadge } from '../../shared/ui/StatusBadge';
import { formatDate, formatMoney } from '../../shared/utils/format';
import {
  allowedSizes,
  buildColorInputFromRows,
  buildVariantMatrixRows,
  countNewVariantMatrixRows,
  deriveSelectedSizesFromRows,
  getIncompatibleSizes,
  getPersistedIncompatibleSizes,
  groupVariantMatrixRows,
  hasDuplicateVariantKeys,
  normalizeMatrixColorInput,
  normalizeSizeForGrid,
  regenerateNewSkusForRows,
  sortSizesForGrid,
  toProductVariantPayload,
  validateVariantQuantities,
  type MatrixColor,
  type VariantMatrixRow,
} from './variantMatrix';
import { applyGeneratedProductSlug } from './productSlugAutofill';
import {
  buildProductCustomerLink,
  copyTextToClipboard,
  getLinkableProductCategories,
  getLinkableProductVariants,
  getProductLinkGeneratorState,
} from './productLinks';

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
  sizeGroup: ProductSizeGroup;
  imageBadgeType: ProductImageBadgeType;
  imageBadgeText: string;
  imageBadgeColor: ProductImageBadgeColor;
  imageBadgePosition: ProductImageBadgePosition;
  status: ProductStatus;
  isListed: boolean;
  isReturnable: boolean;
  tagIds: number[];
}

interface CategoryAssignmentRow {
  localId: number;
  categoryId: string;
  priority: '1' | '2' | '3';
}

interface VariantRow extends VariantMatrixRow {
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
  sizeGroup: 'CLOTHING',
  imageBadgeType: 'none',
  imageBadgeText: '',
  imageBadgeColor: 'purple',
  imageBadgePosition: 'top-left',
  status: 'DRAFT',
  isListed: true,
  isReturnable: true,
  tagIds: [],
};

function createCategoryAssignmentRow(priority: '1' | '2' | '3' = '1'): CategoryAssignmentRow {
  return {
    localId: Date.now() + Math.random(),
    categoryId: '',
    priority,
  };
}

function createVariantLocalId(): number {
  return Date.now() + Math.random();
}

export function ProductEditorPage({ mode, productId, onNavigate, onAuthExpired }: PageProps) {
  const { language, t } = useI18n();
  const [form, setForm] = useState<ProductFormState>(initialForm);
  const [categoryAssignments, setCategoryAssignments] = useState<CategoryAssignmentRow[]>([
    createCategoryAssignmentRow(),
  ]);
  const [variants, setVariants] = useState<VariantRow[]>([]);
  const [matrixColorInput, setMatrixColorInput] = useState('');
  const [selectedMatrixSizes, setSelectedMatrixSizes] = useState<string[]>([]);
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
  const [canRegenerateNewSkus, setCanRegenerateNewSkus] = useState(false);
  const [success, setSuccess] = useState<string | null>(null);
  const [createdProductId, setCreatedProductId] = useState<number | null>(null);
  const [selectedLinkCategoryId, setSelectedLinkCategoryId] = useState('');
  const [selectedLinkVariantId, setSelectedLinkVariantId] = useState('');
  const [linkCopyStatus, setLinkCopyStatus] = useState<'idle' | 'success' | 'error'>('idle');
  const manualSlugEditRef = useRef(false);

  function loadNextProductSlug() {
    if (mode !== 'create') {
      return;
    }

    api.products.generateProductSlugs(1)
      .then((response) => {
        const nextSlug = response.items[0];
        setForm((current) => ({
          ...current,
          slug: applyGeneratedProductSlug({
            mode,
            currentSlug: current.slug,
            generatedSlug: nextSlug,
            wasManuallyEdited: manualSlugEditRef.current,
          }),
        }));
      })
      .catch(() => {
        setFormError(t('productEditor.slugAutofillFailed'));
      });
  }

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
        setCanRegenerateNewSkus(false);

        if (loadedProduct) {
          manualSlugEditRef.current = true;
          const loadedVariants: VariantRow[] = loadedProduct.variants.map((variant) => ({
            localId: variant.id,
            id: variant.id,
            size: variant.size,
            color: variant.color ?? '',
            sku: variant.sku,
            stockQuantity: String(variant.stock_quantity),
            reservedQuantity: String(variant.reserved_quantity),
            isActive: variant.is_active,
          }));
          const loadedSizeGrid = loadedProduct.size_grid ?? 'clothing_alpha';
          const loadedSizeGroup = loadedProduct.size_group ?? 'CLOTHING';

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
            sizeGrid: loadedSizeGrid,
            sizeGroup: loadedSizeGroup,
            imageBadgeType: loadedProduct.image_badge_type ?? 'none',
            imageBadgeText: loadedProduct.image_badge_text ?? '',
            imageBadgeColor:
              loadedProduct.image_badge_color ??
              getDefaultImageBadgeColor(loadedProduct.image_badge_type ?? 'none'),
            imageBadgePosition:
              loadedProduct.image_badge_position ??
              getDefaultImageBadgePosition(loadedProduct.image_badge_type ?? 'none'),
            status: loadedProduct.status,
            isListed: loadedProduct.is_listed ?? true,
            isReturnable: loadedProduct.is_returnable ?? true,
            tagIds: loadedProduct.tags.map((tag) => tag.id),
          });
          setCategoryAssignments(getCategoryRowsFromProduct(loadedProduct));
          setRelatedProductIds(
            (loadedProduct.related_product_ids ?? []).map((relatedId) => String(relatedId)),
          );
          setVariants(loadedVariants);
          setMatrixColorInput(buildColorInputFromRows(loadedVariants));
          setSelectedMatrixSizes(deriveSelectedSizesFromRows(loadedSizeGrid, loadedVariants));
        } else {
          manualSlugEditRef.current = false;
          setProduct(null);
          setForm(initialForm);
          setCategoryAssignments([createCategoryAssignmentRow()]);
          setRelatedProductIds([]);
          setVariants([]);
          setMatrixColorInput('');
          setSelectedMatrixSizes([]);
          loadNextProductSlug();
        }
      })
      .catch(setError)
      .finally(() => setLoading(false));
  }

  useEffect(() => {
    loadFormData();
  }, [mode, productId]);

  const linkCategories = useMemo(() => getLinkableProductCategories(product), [product]);
  const linkVariants = useMemo(() => getLinkableProductVariants(product), [product]);
  const selectedLinkCategory =
    linkCategories.find((category) => String(category.id) === selectedLinkCategoryId) ??
    linkCategories[0] ??
    null;
  const selectedLinkVariant =
    linkVariants.find((variant) => String(variant.id) === selectedLinkVariantId) ??
    linkVariants[0] ??
    null;
  const linkGeneratorState = getProductLinkGeneratorState(product, linkCategories, linkVariants);
  const generatedCustomerLink =
    linkGeneratorState === 'ready' && product?.slug && selectedLinkCategory && selectedLinkVariant
      ? buildProductCustomerLink({
          categorySlug: selectedLinkCategory.slug,
          productSlug: product.slug,
          sku: selectedLinkVariant.sku,
        })
      : '';

  useEffect(() => {
    if (!selectedLinkCategory && selectedLinkCategoryId) {
      setSelectedLinkCategoryId('');
    } else if (selectedLinkCategory && selectedLinkCategoryId !== String(selectedLinkCategory.id)) {
      setSelectedLinkCategoryId(String(selectedLinkCategory.id));
    }

    if (!selectedLinkVariant && selectedLinkVariantId) {
      setSelectedLinkVariantId('');
    } else if (selectedLinkVariant && selectedLinkVariantId !== String(selectedLinkVariant.id)) {
      setSelectedLinkVariantId(String(selectedLinkVariant.id));
    }
  }, [selectedLinkCategory, selectedLinkCategoryId, selectedLinkVariant, selectedLinkVariantId]);

  function updateField<Key extends keyof ProductFormState>(key: Key, value: ProductFormState[Key]) {
    setForm((current) => ({ ...current, [key]: value }));
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
    const persistedIncompatible = getPersistedIncompatibleSizes(variants, nextGrid);
    if (persistedIncompatible.length > 0) {
      setFormError(
        t('productEditor.persistedIncompatibleSizes', {
          sizes: persistedIncompatible.join(', '),
        }),
      );
      return;
    }
    const incompatible = getIncompatibleSizes(variants, nextGrid);
    if (incompatible.length > 0) {
      setFormError(
        t('productEditor.incompatibleSizes', {
          sizes: incompatible.join(', '),
        }),
      );
      return;
    }
    setFormError(null);
    updateField('sizeGrid', nextGrid);
    setSelectedMatrixSizes((current) =>
      sortSizesForGrid(nextGrid, current.filter((size) => normalizeSizeForGrid(nextGrid, size))),
    );
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

  async function copyGeneratedCustomerLink() {
    if (!generatedCustomerLink) {
      return;
    }

    try {
      const copied = await copyTextToClipboard(generatedCustomerLink);
      setLinkCopyStatus(copied ? 'success' : 'error');
    } catch {
      setLinkCopyStatus('error');
    }
  }

  function removeVariant(row: VariantRow) {
    setVariants((current) => {
      if (row.id) {
        return current.map((variant) =>
          variant.localId === row.localId ? { ...variant, remove: true } : variant,
        );
      }

      return current.filter((variant) => variant.localId !== row.localId);
    });
  }

  function toggleMatrixSize(size: string) {
    setSelectedMatrixSizes((current) => {
      const normalized = normalizeSizeForGrid(form.sizeGrid, size);
      if (!normalized) {
        return current;
      }
      const next = current.includes(normalized)
        ? current.filter((currentSize) => currentSize !== normalized)
        : [...current, normalized];
      return sortSizesForGrid(form.sizeGrid, next);
    });
  }

  async function generateVariantMatrix() {
    const normalizedSizes = sortSizesForGrid(form.sizeGrid, selectedMatrixSizes);
    if (normalizedSizes.length === 0) {
      setFormError(t('productEditor.matrixSelectSize'));
      return;
    }

    const normalizedColorInput = normalizeMatrixColorInput(matrixColorInput);
    const newRowCount = countNewVariantMatrixRows(variants, {
      sizeGrid: form.sizeGrid,
      selectedSizes: normalizedSizes,
      colorInput: normalizedColorInput,
    });

    try {
      const generatedSkus =
        newRowCount > 0 ? (await api.products.generateVariantSkus(newRowCount)).items : [];
      setSelectedMatrixSizes(normalizedSizes);
      setMatrixColorInput(normalizedColorInput);
      setVariants((current) =>
        buildVariantMatrixRows(current, {
          sizeGrid: form.sizeGrid,
          selectedSizes: normalizedSizes,
          colorInput: normalizedColorInput,
          productName: form.name,
          productSlug: form.slug,
          createLocalId: createVariantLocalId,
          generatedSkus,
        }),
      );
      setCanRegenerateNewSkus(false);
      setFormError(null);
    } catch (requestError) {
      setFormError(
        requestError instanceof Error
          ? requestError.message
          : 'Unable to generate numeric SKU values.',
      );
    }
  }

  async function regenerateNewVariantSkus() {
    const newRowCount = variants.filter(
      (variant) => !variant.id && !variant.remove && variant.size.trim(),
    ).length;

    try {
      const generatedSkus =
        newRowCount > 0 ? (await api.products.generateVariantSkus(newRowCount)).items : [];
      setVariants((current) =>
        regenerateNewSkusForRows(current, {
          generatedSkus,
        }),
      );
      setCanRegenerateNewSkus(false);
      setFormError(null);
    } catch (requestError) {
      setFormError(
        requestError instanceof Error
          ? requestError.message
          : 'Unable to generate numeric SKU values.',
      );
    }
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSaving(true);
    setError(null);
    setFormError(null);
    setCanRegenerateNewSkus(false);
    setSuccess(null);

    if (!form.name.trim() || (mode === 'edit' && !form.slug.trim()) || !form.basePrice.trim()) {
      setFormError(t(mode === 'edit' ? 'productEditor.required' : 'productEditor.createRequired'));
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
    if (!isImageBadgeConfigurationValid({ type: form.imageBadgeType, text: form.imageBadgeText, color: form.imageBadgeColor, position: form.imageBadgePosition })) {
      setFormError(t('productEditor.badgeCustomRequired'));
      setSaving(false);
      return;
    }

    const quantityValidation = validateVariantQuantities(variants);
    if (!quantityValidation.ok) {
      setFormError(
        t(`productEditor.quantity.${quantityValidation.reason}`, {
          variant: formatVariantValidationTarget(
            quantityValidation.size,
            quantityValidation.color,
            t,
          ),
        }),
      );
      setSaving(false);
      return;
    }

    if (hasDuplicateVariantKeys(variants)) {
      setFormError(t('productEditor.duplicateVariants'));
      setSaving(false);
      return;
    }

    const primaryCategoryId =
      [...normalizedCategories].sort((left, right) => left.priority - right.priority)[0]
        ?.category_id ?? null;
    const trimmedSlug = form.slug.trim();

    try {
      const payload = {
        name: form.name.trim(),
        ...(trimmedSlug ? { slug: trimmedSlug } : {}),
        brand: form.brand.trim() || null,
        description: form.description.trim() || null,
        base_price: form.basePrice.trim(),
        old_price: form.oldPrice.trim() || null,
        search_priority: parseSearchPriority(form.searchPriority),
        search_aliases: normalizeSearchAliases(form.searchAliases),
        size_grid: form.sizeGrid,
        size_group: form.sizeGroup,
        image_badge_type: form.imageBadgeType,
        image_badge_text: form.imageBadgeType === 'custom' ? normalizeImageBadgeText(form.imageBadgeText) : null,
        image_badge_color: form.imageBadgeColor,
        image_badge_position: form.imageBadgePosition,
        status: form.status,
        is_listed: form.isListed,
        is_returnable: form.isReturnable,
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
      if (isDuplicateSkuError(requestError)) {
        setFormError(t('productEditor.duplicateSkuBackend'));
        setCanRegenerateNewSkus(true);
      } else {
        setError(requestError);
      }
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

      const payload = toProductVariantPayload(row);
      if (!payload) {
        continue;
      }

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
  const matrixGrouping = groupVariantMatrixRows(visibleVariants, {
    sizeGrid: form.sizeGrid,
    selectedSizes: selectedMatrixSizes,
    colorInput: matrixColorInput,
  });
  const matrixRowCount = matrixGrouping.groups.reduce(
    (total, group) => total + group.rows.length,
    0,
  );
  const expectedMatrixRowCount = selectedMatrixSizes.length * matrixGrouping.groups.length;
  const activeCropFile = pendingCropFiles[0] ?? null;

  return (
    <form className="page-stack" onSubmit={handleSubmit}>
      {formError ? (
        <div className="form-error form-error-with-action">
          <span>{formError}</span>
          {canRegenerateNewSkus ? (
            <button className="button button-secondary" type="button" onClick={regenerateNewVariantSkus}>
              {t('productEditor.regenerateNewSkus')}
            </button>
          ) : null}
        </div>
      ) : null}
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
                onChange={(event) => updateField('name', event.target.value)}
              />
            </label>
            <label className="field">
              <span>{t('productEditor.slug')}</span>
              <input
                value={form.slug}
                onChange={(event) => {
                  manualSlugEditRef.current = true;
                  updateField('slug', event.target.value);
                }}
              />
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
            <div className="form-pair-row field-wide product-settings-row">
              <label className="toggle-label product-setting-toggle">
                <input
                  checked={form.isListed}
                  type="checkbox"
                  onChange={(event) => updateField('isListed', event.target.checked)}
                />
                <span>{t('productEditor.isListed')}</span>
              </label>
              <label className="toggle-label product-setting-toggle">
                <input
                  checked={form.isReturnable}
                  type="checkbox"
                  onChange={(event) => updateField('isReturnable', event.target.checked)}
                />
                <span>{t('productEditor.isReturnable')}</span>
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
              <div>
                <dt>{t('productEditor.isListed')}</dt>
                <dd>{product.is_listed ? t('common.yes') : t('common.no')}</dd>
              </div>
              <div>
                <dt>{t('productEditor.isReturnable')}</dt>
                <dd>{product.is_returnable ? t('common.yes') : t('common.no')}</dd>
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

      <details className="panel product-links-panel" open={Boolean(generatedCustomerLink)}>
        <summary className="product-links-summary">
          <span>{t('productEditor.productLinks')}</span>
          <small>{t('productEditor.productLinksHint')}</small>
        </summary>
        {linkGeneratorState === 'save_first' ? (
          <p className="muted-text">{t('productEditor.productLinksSaveFirst')}</p>
        ) : linkGeneratorState === 'needs_category' ? (
          <p className="muted-text">{t('productEditor.productLinksNeedCategory')}</p>
        ) : linkGeneratorState === 'needs_variant' ? (
          <p className="muted-text">{t('productEditor.productLinksNeedVariant')}</p>
        ) : (
          <div className="product-link-generator">
            <label className="field">
              <span>{t('common.category')}</span>
              <select
                value={selectedLinkCategory ? String(selectedLinkCategory.id) : ''}
                onChange={(event) => {
                  setSelectedLinkCategoryId(event.target.value);
                  setLinkCopyStatus('idle');
                }}
              >
                {linkCategories.map((category) => (
                  <option key={category.id} value={category.id}>
                    {category.name}
                  </option>
                ))}
              </select>
            </label>
            <label className="field">
              <span>{t('productEditor.sku')}</span>
              <select
                value={selectedLinkVariant ? String(selectedLinkVariant.id) : ''}
                onChange={(event) => {
                  setSelectedLinkVariantId(event.target.value);
                  setLinkCopyStatus('idle');
                }}
              >
                {linkVariants.map((variant) => (
                  <option key={variant.id} value={variant.id}>
                    {formatCustomerLinkVariantLabel(variant, t)}
                  </option>
                ))}
              </select>
            </label>
            <label className="field field-wide product-link-preview">
              <span>{t('productEditor.productLinksPreview')}</span>
              <input readOnly value={generatedCustomerLink} />
            </label>
            <div className="product-link-actions">
              <button
                className="button button-primary"
                disabled={!generatedCustomerLink}
                type="button"
                onClick={() => void copyGeneratedCustomerLink()}
              >
                {t('productEditor.productLinksCopy')}
              </button>
              {linkCopyStatus !== 'idle' ? (
                <span
                  className={`product-link-copy-status product-link-copy-status-${linkCopyStatus}`}
                  role="status"
                >
                  {linkCopyStatus === 'success'
                    ? t('productEditor.productLinksCopied')
                    : t('productEditor.productLinksCopyFailed')}
                </span>
              ) : null}
            </div>
          </div>
        )}
      </details>

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
        <ImageBadgeConfigurator
          value={{ type: form.imageBadgeType, text: form.imageBadgeText, color: form.imageBadgeColor, position: form.imageBadgePosition }}
          onChange={(next) => setForm((current) => ({ ...current, imageBadgeType: next.type, imageBadgeText: next.text, imageBadgeColor: next.color, imageBadgePosition: next.position }))}
        />
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
          <div>
            <h2>{t('productEditor.variantsStock')}</h2>
            <p className="muted-text">
              {t('productEditor.matrixSummary', {
                count: matrixRowCount,
                expected: expectedMatrixRowCount,
              })}
            </p>
          </div>
          <button className="button button-primary" type="button" onClick={generateVariantMatrix}>
            {t('productEditor.generateMatrix')}
          </button>
        </div>

        <div className="variant-builder-grid">
          <label className="field">
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
          <label className="field">
            <span>{t('productEditor.sizeGroup')}</span>
            <select
              value={form.sizeGroup}
              onChange={(event) => updateField('sizeGroup', event.target.value as ProductSizeGroup)}
            >
              <option value="CLOTHING">{t('productEditor.sizeGroupClothing')}</option>
              <option value="FOOTWEAR">{t('productEditor.sizeGroupFootwear')}</option>
              <option value="ONE_SIZE">{t('productEditor.sizeGroupOneSize')}</option>
            </select>
          </label>
          <label className="field">
            <span>{t('productEditor.matrixColors')}</span>
            <input
              autoComplete="off"
              placeholder={t('productEditor.matrixColorsPlaceholder')}
              value={matrixColorInput}
              onBlur={() => setMatrixColorInput(normalizeMatrixColorInput(matrixColorInput))}
              onChange={(event) => setMatrixColorInput(event.target.value)}
            />
          </label>
          <div className="field field-wide">
            <span>{t('productEditor.matrixSizes')}</span>
            <div className="size-chip-grid" role="group" aria-label={t('productEditor.matrixSizes')}>
              {allowedSizes(form.sizeGrid).map((size) => {
                const selected = selectedMatrixSizes.includes(size);
                return (
                  <button
                    className={`size-chip ${selected ? 'size-chip-selected' : ''}`}
                    key={size}
                    type="button"
                    aria-pressed={selected}
                    onClick={() => toggleMatrixSize(size)}
                  >
                    {formatSizeLabel(size, t)}
                  </button>
                );
              })}
            </div>
          </div>
        </div>
        <>
            {matrixRowCount > 0 ? (
              <div className="variant-matrix-list">
                {matrixGrouping.groups
                  .filter((group) => group.rows.length > 0)
                  .map((group) => (
                    <div className="variant-matrix-block" key={group.color.key}>
                      <div className="variant-matrix-heading">
                        <h3>{formatColorBlockTitle(group.color, t)}</h3>
                        <span>
                          {t('productEditor.matrixRowsCount', { count: group.rows.length })}
                        </span>
                      </div>
                      <div className="variant-matrix-table">
                        <table>
                          <thead>
                            <tr>
                              <th>{t('productEditor.size')}</th>
                              <th>{t('productEditor.sku')}</th>
                              <th>{t('productEditor.stock')}</th>
                              <th>{t('productEditor.reserved')}</th>
                              <th>{t('common.active')}</th>
                              <th>{t('common.actions')}</th>
                            </tr>
                          </thead>
                          <tbody>
                            {group.rows.map((variant) => (
                              <tr key={variant.localId}>
                                <td>
                                  <strong>{formatSizeLabel(variant.size, t)}</strong>
                                </td>
                                <td>
                                  <input
                                    className="sku-input"
                                    readOnly
                                    title={t('productEditor.skuReadOnly')}
                                    value={variant.sku}
                                  />
                                </td>
                                <td>
                                  <input
                                    inputMode="numeric"
                                    min="0"
                                    step="1"
                                    type="number"
                                    value={variant.stockQuantity}
                                    aria-label={t('productEditor.stockForVariant', {
                                      variant: formatVariantValidationTarget(
                                        variant.size,
                                        variant.color,
                                        t,
                                      ),
                                    })}
                                    onChange={(event) =>
                                      updateVariant(variant.localId, {
                                        stockQuantity: event.target.value,
                                      })
                                    }
                                  />
                                </td>
                                <td>
                                  <input
                                    inputMode="numeric"
                                    max={Math.max(0, Number(variant.stockQuantity || 0))}
                                    min="0"
                                    step="1"
                                    type="number"
                                    value={variant.reservedQuantity}
                                    aria-label={t('productEditor.reservedForVariant', {
                                      variant: formatVariantValidationTarget(
                                        variant.size,
                                        variant.color,
                                        t,
                                      ),
                                    })}
                                    onChange={(event) =>
                                      updateVariant(variant.localId, {
                                        reservedQuantity: event.target.value,
                                      })
                                    }
                                  />
                                </td>
                                <td>
                                  <label className="toggle-label compact-toggle">
                                    <input
                                      checked={variant.isActive}
                                      type="checkbox"
                                      onChange={(event) =>
                                        updateVariant(variant.localId, {
                                          isActive: event.target.checked,
                                        })
                                      }
                                    />
                                    {variant.isActive ? t('common.active') : t('common.inactive')}
                                  </label>
                                </td>
                                <td>
                                  <button
                                    className="text-button danger-text"
                                    type="button"
                                    onClick={() => removeVariant(variant)}
                                  >
                                    {t('common.remove')}
                                  </button>
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  ))}
              </div>
            ) : (
              <p className="muted-text variant-empty-text">{t('productEditor.matrixNoRows')}</p>
            )}

            {matrixGrouping.outsideRows.length > 0 ? (
              <div className="variant-matrix-block variant-matrix-block-warning">
                <div className="variant-matrix-heading">
                  <div>
                    <h3>{t('productEditor.outsideMatrix')}</h3>
                    <p className="muted-text">{t('productEditor.outsideMatrixHint')}</p>
                  </div>
                  <span>
                    {t('productEditor.matrixRowsCount', {
                      count: matrixGrouping.outsideRows.length,
                    })}
                  </span>
                </div>
                <div className="variant-matrix-table">
                  <table>
                    <thead>
                      <tr>
                        <th>{t('productEditor.size')}</th>
                        <th>{t('productEditor.color')}</th>
                        <th>{t('productEditor.sku')}</th>
                        <th>{t('productEditor.stock')}</th>
                        <th>{t('productEditor.reserved')}</th>
                        <th>{t('common.active')}</th>
                        <th>{t('common.actions')}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {matrixGrouping.outsideRows.map((variant) => (
                        <tr key={variant.localId}>
                          <td>
                            <strong>{formatSizeLabel(variant.size, t)}</strong>
                          </td>
                          <td>{formatColorLabel(variant.color, t)}</td>
                          <td>
                            <input
                              className="sku-input"
                              readOnly
                              title={t('productEditor.skuReadOnly')}
                              value={variant.sku}
                            />
                          </td>
                          <td>
                            <input
                              inputMode="numeric"
                              min="0"
                              step="1"
                              type="number"
                              value={variant.stockQuantity}
                              onChange={(event) =>
                                updateVariant(variant.localId, {
                                  stockQuantity: event.target.value,
                                })
                              }
                            />
                          </td>
                          <td>
                            <input
                              inputMode="numeric"
                              max={Math.max(0, Number(variant.stockQuantity || 0))}
                              min="0"
                              step="1"
                              type="number"
                              value={variant.reservedQuantity}
                              onChange={(event) =>
                                updateVariant(variant.localId, {
                                  reservedQuantity: event.target.value,
                                })
                              }
                            />
                          </td>
                          <td>
                            <label className="toggle-label compact-toggle">
                              <input
                                checked={variant.isActive}
                                type="checkbox"
                                onChange={(event) =>
                                  updateVariant(variant.localId, {
                                    isActive: event.target.checked,
                                  })
                                }
                              />
                              {variant.isActive ? t('common.active') : t('common.inactive')}
                            </label>
                          </td>
                          <td>
                            <button
                              className="text-button danger-text"
                              type="button"
                              onClick={() => removeVariant(variant)}
                            >
                              {t('common.remove')}
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            ) : null}
        </>
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

function formatSizeLabel(size: string, t: ReturnType<typeof useI18n>['t']): string {
  return size === 'ONE_SIZE' ? t('productEditor.oneSize') : size || t('common.notProvided');
}

function formatColorLabel(color: string, t: ReturnType<typeof useI18n>['t']): string {
  return color.trim() || t('productEditor.noColor');
}

function formatColorBlockTitle(color: MatrixColor, t: ReturnType<typeof useI18n>['t']): string {
  if (color.isNoColor) {
    return t('productEditor.noColorBlock');
  }

  return t('productEditor.colorBlockTitle', { color: color.label });
}

function formatVariantValidationTarget(
  size: string,
  color: string,
  t: ReturnType<typeof useI18n>['t'],
): string {
  return `${formatSizeLabel(size, t)} / ${formatColorLabel(color, t)}`;
}

function formatCustomerLinkVariantLabel(
  variant: ProductVariant,
  t: ReturnType<typeof useI18n>['t'],
): string {
  const availability = !variant.is_active
    ? t('common.inactive')
    : variant.available_quantity > 0
      ? t('productEditor.productLinksAvailable')
      : t('productEditor.productLinksUnavailable');
  return [
    variant.sku,
    formatColorLabel(variant.color ?? '', t),
    formatSizeLabel(variant.size, t),
    availability,
  ].join(' · ');
}

function isDuplicateSkuError(error: unknown): boolean {
  if (!(error instanceof ApiError)) {
    return false;
  }

  return error.status === 409 && error.message.toLocaleLowerCase('en-US').includes('sku');
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
