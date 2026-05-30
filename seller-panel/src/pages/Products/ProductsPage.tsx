import { FormEvent, useEffect, useState } from 'react';
import { api, resolveMediaUrl } from '../../shared/api';
import type { Category, Product, ProductStatus, Tag } from '../../shared/api';
import { ErrorState, LoadingState } from '../../shared/ui/DataState';
import { StatusBadge } from '../../shared/ui/StatusBadge';
import { formatDate, formatMoney } from '../../shared/utils/format';

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
      setNotice('Product status updated.');
      loadProducts();
    } catch (requestError) {
      setError(requestError);
    }
  }

  async function archiveProduct(productId: number) {
    setNotice(null);
    try {
      await api.products.archive(productId);
      setNotice('Product archived.');
      loadProducts();
    } catch (requestError) {
      setError(requestError);
    }
  }

  if (loading) return <LoadingState title="Loading products" />;
  if (error) {
    return <ErrorState error={error} onRetry={loadProducts} onAuthExpired={onAuthExpired} />;
  }

  return (
    <div className="page-stack">
      <div className="page-toolbar">
        <form className="filters-row" onSubmit={applyFilters}>
          <label>
            <span>Search</span>
            <input
              value={draftFilters.search}
              onChange={(event) =>
                setDraftFilters((current) => ({ ...current, search: event.target.value }))
              }
              placeholder="Name or slug"
            />
          </label>
          <label>
            <span>Status</span>
            <select
              value={draftFilters.status}
              onChange={(event) =>
                setDraftFilters((current) => ({
                  ...current,
                  status: event.target.value as ProductFilters['status'],
                }))
              }
            >
              <option value="">All statuses</option>
              <option value="DRAFT">Draft</option>
              <option value="ACTIVE">Active</option>
              <option value="OUT_OF_STOCK">Out of stock</option>
              <option value="ARCHIVED">Archived</option>
            </select>
          </label>
          <label>
            <span>Category</span>
            <select
              value={draftFilters.categoryId}
              onChange={(event) =>
                setDraftFilters((current) => ({ ...current, categoryId: event.target.value }))
              }
            >
              <option value="">All categories</option>
              {categories.map((category) => (
                <option key={category.id} value={category.id}>
                  {category.name}
                </option>
              ))}
            </select>
          </label>
          <label>
            <span>Tag</span>
            <select
              value={draftFilters.tagId}
              onChange={(event) =>
                setDraftFilters((current) => ({ ...current, tagId: event.target.value }))
              }
            >
              <option value="">All tags</option>
              {tags.map((tag) => (
                <option key={tag.id} value={tag.id}>
                  {tag.name}
                </option>
              ))}
            </select>
          </label>
          <button className="button button-secondary" type="submit">
            Apply
          </button>
        </form>
        <button className="button button-primary" type="button" onClick={() => onNavigate('/products/new')}>
          Add Product
        </button>
      </div>

      {notice ? <div className="success-banner">{notice}</div> : null}

      <div className="table-panel">
        <table>
          <thead>
            <tr>
              <th>Image</th>
              <th>Product name</th>
              <th>Category</th>
              <th>Price</th>
              <th>Variants / stock</th>
              <th>Status</th>
              <th>Tags</th>
              <th>Updated</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {products.length === 0 ? (
              <tr>
                <td colSpan={9}>
                  <div className="empty-table">No products match the current filters.</div>
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
                          src={resolveMediaUrl(image.url)}
                          alt={image.alt_text ?? product.name}
                        />
                      ) : (
                        <div className="table-image table-image-empty">No image</div>
                      )}
                    </td>
                    <td>
                      <strong>{product.name}</strong>
                      <small>{product.slug}</small>
                    </td>
                    <td>{product.category?.name ?? 'Unassigned'}</td>
                    <td>{formatMoney(product.base_price)}</td>
                    <td>
                      <strong>{product.variants.length}</strong>
                      <small>{totalStock} available</small>
                    </td>
                    <td>
                      <StatusBadge status={product.status} />
                    </td>
                    <td>
                      <div className="tag-list">
                        {product.tags.length > 0
                          ? product.tags.map((tag) => <span key={tag.id}>{tag.name}</span>)
                          : 'No tags'}
                      </div>
                    </td>
                    <td>{formatDate(product.updated_at)}</td>
                    <td>
                      <div className="table-actions">
                        <button
                          className="text-button"
                          type="button"
                          onClick={() => onNavigate(`/products/${product.id}/edit`)}
                        >
                          Edit
                        </button>
                        <select
                          aria-label={`Change status for ${product.name}`}
                          value={product.status}
                          onChange={(event) =>
                            updateStatus(product.id, event.target.value as ProductStatus)
                          }
                        >
                          <option value="DRAFT">Draft</option>
                          <option value="ACTIVE">Active</option>
                          <option value="OUT_OF_STOCK">Out of stock</option>
                          <option value="ARCHIVED">Archived</option>
                        </select>
                        <button
                          className="text-button danger-text"
                          type="button"
                          onClick={() => archiveProduct(product.id)}
                        >
                          Archive
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
