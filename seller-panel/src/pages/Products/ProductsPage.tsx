import { FormEvent, useEffect, useState } from 'react';
import { api, resolveMediaUrl } from '../../shared/api';
import type { Category, Product, ProductStatus, Tag } from '../../shared/api';
import { labelForEnum, useI18n } from '../../shared/i18n';
import { ErrorState, LoadingState } from '../../shared/ui/DataState';
import { StatusBadge } from '../../shared/ui/StatusBadge';
import { formatDate, formatMoney } from '../../shared/utils/format';
import { InternalLink } from '../../shared/navigation/InternalLink';

interface PageProps {
  onNavigate: (path: string) => void;
  onAuthExpired: () => void;
}

interface ProductFilters {
  search: string;
  status: '' | ProductStatus;
  categoryId: string;
  tagId: string;
}

const emptyFilters: ProductFilters = {
  search: '',
  status: '',
  categoryId: '',
  tagId: '',
};

export function ProductsPage({ onNavigate, onAuthExpired }: PageProps) {
  const { language, t } = useI18n();
  const [products, setProducts] = useState<Product[]>([]);
  const [categories, setCategories] = useState<Category[]>([]);
  const [tags, setTags] = useState<Tag[]>([]);
  const [filters, setFilters] = useState<ProductFilters>(emptyFilters);
  const [draftFilters, setDraftFilters] = useState<ProductFilters>(emptyFilters);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<unknown>(null);
  const [notice, setNotice] = useState<string | null>(null);

  function loadProducts() {
    setLoading(true);
    setError(null);

    Promise.all([
      api.products.listAdmin({
        limit: 100,
        offset: 0,
        search: filters.search,
        status: filters.status,
        category_id: filters.categoryId,
        tag_id: filters.tagId,
      }),
      api.categories.list(),
      api.tags.list(),
    ])
      .then(([productList, categoryList, tagList]) => {
        setProducts(productList.items);
        setCategories(categoryList);
        setTags(tagList);
      })
      .catch(setError)
      .finally(() => setLoading(false));
  }

  useEffect(() => {
    loadProducts();
  }, [filters]);

  function applyFilters(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setFilters(draftFilters);
  }

  async function updateStatus(productId: number, status: ProductStatus) {
    setNotice(null);
    try {
      await api.products.updateStatus(productId, status);
      setNotice(t('products.statusUpdated'));
      loadProducts();
    } catch (requestError) {
      setError(requestError);
    }
  }

  async function archiveProduct(productId: number) {
    setNotice(null);
    try {
      await api.products.archive(productId);
      setNotice(t('products.archived'));
      loadProducts();
    } catch (requestError) {
      setError(requestError);
    }
  }

  if (loading) return <LoadingState title={t('products.loading')} />;
  if (error) {
    return <ErrorState error={error} onRetry={loadProducts} onAuthExpired={onAuthExpired} />;
  }

  return (
    <div className="page-stack">
      <div className="page-toolbar">
        <form className="filters-row" onSubmit={applyFilters}>
          <label>
            <span>{t('common.search')}</span>
            <input
              value={draftFilters.search}
              onChange={(event) =>
                setDraftFilters((current) => ({ ...current, search: event.target.value }))
              }
              placeholder={t('products.searchPlaceholder')}
            />
          </label>
          <label>
            <span>{t('common.status')}</span>
            <select
              value={draftFilters.status}
              onChange={(event) =>
                setDraftFilters((current) => ({
                  ...current,
                  status: event.target.value as ProductFilters['status'],
                }))
              }
            >
              <option value="">{t('common.allStatuses')}</option>
              <option value="DRAFT">{labelForEnum('DRAFT', t)}</option>
              <option value="ACTIVE">{labelForEnum('ACTIVE', t)}</option>
              <option value="OUT_OF_STOCK">{labelForEnum('OUT_OF_STOCK', t)}</option>
              <option value="ARCHIVED">{labelForEnum('ARCHIVED', t)}</option>
            </select>
          </label>
          <label>
            <span>{t('common.category')}</span>
            <select
              value={draftFilters.categoryId}
              onChange={(event) =>
                setDraftFilters((current) => ({ ...current, categoryId: event.target.value }))
              }
            >
              <option value="">{t('products.allCategories')}</option>
              {categories.map((category) => (
                <option key={category.id} value={category.id}>
                  {category.name}
                </option>
              ))}
            </select>
          </label>
          <label>
            <span>{t('common.tag')}</span>
            <select
              value={draftFilters.tagId}
              onChange={(event) =>
                setDraftFilters((current) => ({ ...current, tagId: event.target.value }))
              }
            >
              <option value="">{t('products.allTags')}</option>
              {tags.map((tag) => (
                <option key={tag.id} value={tag.id}>
                  {tag.name}
                </option>
              ))}
            </select>
          </label>
          <button className="button button-secondary" type="submit">
            {t('common.apply')}
          </button>
        </form>
        <InternalLink className="button button-primary" href="/products/new" onNavigate={onNavigate}>
          {t('products.addProduct')}
        </InternalLink>
      </div>

      {notice ? <div className="success-banner">{notice}</div> : null}

      <div className="table-panel">
        <table>
          <thead>
            <tr>
              <th>{t('common.image')}</th>
              <th>{t('products.productName')}</th>
              <th>{t('common.category')}</th>
              <th>{t('products.price')}</th>
              <th>{t('products.variantsStock')}</th>
              <th>{t('common.status')}</th>
              <th>{t('products.tags')}</th>
              <th>{t('common.updated')}</th>
              <th>{t('common.actions')}</th>
            </tr>
          </thead>
          <tbody>
            {products.length === 0 ? (
              <tr>
                <td colSpan={9}>
                  <div className="empty-table">{t('products.empty')}</div>
                </td>
              </tr>
            ) : (
              products.map((product) => {
                const image = product.images.find((item) => item.is_primary) ?? product.images[0];
                const totalStock = product.variants.reduce(
                  (sum, variant) => sum + variant.available_quantity,
                  0,
                );

                return (
                  <tr key={product.id}>
                    <td>
                      {image ? (
                        <img
                          className="table-image"
                          src={resolveMediaUrl(image.thumbnail_url ?? image.card_url ?? image.url)}
                          alt={image.alt_text ?? product.name}
                          width={58}
                          height={72}
                          loading="lazy"
                          decoding="async"
                        />
                      ) : (
                        <div className="table-image table-image-empty">{t('products.noImage')}</div>
                      )}
                    </td>
                    <td>
                      <strong>{product.name}</strong>
                      <small>{product.slug}</small>
                    </td>
                    <td>{formatProductCategories(product) || t('products.unassigned')}</td>
                    <td>
                      <span className="price-stack">
                        {product.old_price ? (
                          <span className="old-price">{formatMoney(product.old_price, language)}</span>
                        ) : null}
                        <strong>{formatMoney(product.base_price, language)}</strong>
                      </span>
                      <small>{t('productEditor.searchPriority')}: {product.search_priority ?? 2}</small>
                    </td>
                    <td>
                      <strong>{product.variants.length}</strong>
                      <small>{t('products.available', { count: totalStock })}</small>
                    </td>
                    <td>
                      <StatusBadge status={product.status} />
                      {!product.is_listed || !product.is_returnable ? (
                        <div className="product-state-badges">
                          {!product.is_listed ? (
                            <span className="product-state-badge">{t('products.hiddenBadge')}</span>
                          ) : null}
                          {!product.is_returnable ? (
                            <span className="product-state-badge product-state-badge-warning">
                              {t('products.nonReturnableBadge')}
                            </span>
                          ) : null}
                        </div>
                      ) : null}
                    </td>
                    <td>
                      <div className="tag-list">
                        {product.tags.length > 0
                          ? product.tags.map((tag) => <span key={tag.id}>{tag.name}</span>)
                          : t('products.noTags')}
                      </div>
                    </td>
                    <td>{formatDate(product.updated_at, language)}</td>
                    <td>
                      <div className="table-actions">
                        <InternalLink
                          className="text-button"
                          href={`/products/${product.id}/edit`}
                          onNavigate={onNavigate}
                        >
                          {t('common.edit')}
                        </InternalLink>
                        <select
                          aria-label={t('products.changeStatus', { name: product.name })}
                          value={product.status}
                          onChange={(event) =>
                            updateStatus(product.id, event.target.value as ProductStatus)
                          }
                        >
                          <option value="DRAFT">{labelForEnum('DRAFT', t)}</option>
                          <option value="ACTIVE">{labelForEnum('ACTIVE', t)}</option>
                          <option value="OUT_OF_STOCK">{labelForEnum('OUT_OF_STOCK', t)}</option>
                          <option value="ARCHIVED">{labelForEnum('ARCHIVED', t)}</option>
                        </select>
                        <button
                          className="text-button danger-text"
                          type="button"
                          onClick={() => archiveProduct(product.id)}
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

function formatProductCategories(product: Product) {
  const names =
    product.categories
      ?.slice()
      .sort((left, right) => left.priority - right.priority)
      .map((assignment) => assignment.category?.name)
      .filter(Boolean) ?? [];

  if (names.length > 0) {
    return names.join(', ');
  }

  return product.category?.name ?? '';
}
