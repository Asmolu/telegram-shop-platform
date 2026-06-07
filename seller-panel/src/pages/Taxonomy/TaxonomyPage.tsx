import { FormEvent, useEffect, useState } from 'react';
import { api } from '../../shared/api';
import type { Category, CategoryPayload, Tag, TagPayload } from '../../shared/api';
import { useI18n } from '../../shared/i18n';
import { ErrorState, LoadingState } from '../../shared/ui/DataState';
import { formatDate, slugify } from '../../shared/utils/format';

interface PageProps {
  onAuthExpired: () => void;
}

interface CategoryFormState {
  name: string;
  slug: string;
  description: string;
}

interface TagFormState {
  name: string;
  slug: string;
}

const initialCategoryForm: CategoryFormState = {
  name: '',
  slug: '',
  description: '',
};

const initialTagForm: TagFormState = {
  name: '',
  slug: '',
};

export function TaxonomyPage({ onAuthExpired }: PageProps) {
  const { language, t } = useI18n();
  const [categories, setCategories] = useState<Category[]>([]);
  const [tags, setTags] = useState<Tag[]>([]);
  const [editingCategory, setEditingCategory] = useState<Category | null>(null);
  const [editingTag, setEditingTag] = useState<Tag | null>(null);
  const [categoryForm, setCategoryForm] = useState<CategoryFormState>(initialCategoryForm);
  const [tagForm, setTagForm] = useState<TagFormState>(initialTagForm);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState<string | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [categoryError, setCategoryError] = useState<string | null>(null);
  const [tagError, setTagError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  function loadTaxonomy() {
    setLoading(true);
    setError(null);

    Promise.all([api.categories.list(), api.tags.list()])
      .then(([categoryList, tagList]) => {
        setCategories(categoryList);
        setTags(tagList);
      })
      .catch(setError)
      .finally(() => setLoading(false));
  }

  useEffect(() => {
    loadTaxonomy();
  }, []);

  function selectCategory(category: Category) {
    setEditingCategory(category);
    setCategoryForm({
      name: category.name,
      slug: category.slug,
      description: category.description ?? '',
    });
    setCategoryError(null);
  }

  function selectTag(tag: Tag) {
    setEditingTag(tag);
    setTagForm({
      name: tag.name,
      slug: tag.slug,
    });
    setTagError(null);
  }

  function resetCategoryForm() {
    setEditingCategory(null);
    setCategoryForm(initialCategoryForm);
    setCategoryError(null);
  }

  function resetTagForm() {
    setEditingTag(null);
    setTagForm(initialTagForm);
    setTagError(null);
  }

  async function submitCategory(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setCategoryError(null);
    setNotice(null);

    if (!categoryForm.name.trim() || !categoryForm.slug.trim()) {
      setCategoryError(t('taxonomy.categoryRequired'));
      return;
    }

    setSaving('category');
    const payload: CategoryPayload = {
      name: categoryForm.name.trim(),
      slug: categoryForm.slug.trim(),
      description: categoryForm.description.trim() || null,
    };

    try {
      if (editingCategory) {
        await api.categories.update(editingCategory.id, payload);
        setNotice(t('taxonomy.notice.categoryUpdated'));
      } else {
        await api.categories.create(payload);
        setNotice(t('taxonomy.notice.categoryCreated'));
      }
      resetCategoryForm();
      loadTaxonomy();
    } catch (requestError) {
      setError(requestError);
    } finally {
      setSaving(null);
    }
  }

  async function submitTag(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setTagError(null);
    setNotice(null);

    if (!tagForm.name.trim() || !tagForm.slug.trim()) {
      setTagError(t('taxonomy.tagRequired'));
      return;
    }

    setSaving('tag');
    const payload: TagPayload = {
      name: tagForm.name.trim(),
      slug: tagForm.slug.trim(),
    };

    try {
      if (editingTag) {
        await api.tags.update(editingTag.id, payload);
        setNotice(t('taxonomy.notice.tagUpdated'));
      } else {
        await api.tags.create(payload);
        setNotice(t('taxonomy.notice.tagCreated'));
      }
      resetTagForm();
      loadTaxonomy();
    } catch (requestError) {
      setError(requestError);
    } finally {
      setSaving(null);
    }
  }

  async function deleteCategory(category: Category) {
    if (!window.confirm(t('taxonomy.deleteCategoryConfirm', { name: category.name }))) {
      return;
    }

    setNotice(null);
    try {
      await api.categories.delete(category.id);
      setNotice(t('taxonomy.notice.categoryDeleted'));
      if (editingCategory?.id === category.id) {
        resetCategoryForm();
      }
      loadTaxonomy();
    } catch (requestError) {
      setError(requestError);
    }
  }

  async function deleteTag(tag: Tag) {
    if (!window.confirm(t('taxonomy.deleteTagConfirm', { name: tag.name }))) {
      return;
    }

    setNotice(null);
    try {
      await api.tags.delete(tag.id);
      setNotice(t('taxonomy.notice.tagDeleted'));
      if (editingTag?.id === tag.id) {
        resetTagForm();
      }
      loadTaxonomy();
    } catch (requestError) {
      setError(requestError);
    }
  }

  if (loading) return <LoadingState title={t('taxonomy.loading')} />;
  if (error) {
    return <ErrorState error={error} onRetry={loadTaxonomy} onAuthExpired={onAuthExpired} />;
  }

  return (
    <div className="page-stack">
      {notice ? <div className="success-banner">{notice}</div> : null}

      <div className="taxonomy-grid">
        <section className="table-panel">
          <div className="section-heading table-heading">
            <div>
              <h2>{t('taxonomy.categoriesTitle')}</h2>
              <p>{t('customerNotifications.rows', { count: categories.length })}</p>
            </div>
          </div>
          <table>
            <thead>
              <tr>
                <th>{t('common.name')}</th>
                <th>{t('productEditor.slug')}</th>
                <th>{t('common.description')}</th>
                <th>{t('common.updated')}</th>
                <th>{t('common.actions')}</th>
              </tr>
            </thead>
            <tbody>
              {categories.length === 0 ? (
                <tr>
                  <td colSpan={5}>
                    <div className="empty-table">{t('taxonomy.emptyCategories')}</div>
                  </td>
                </tr>
              ) : (
                categories.map((category) => (
                  <tr key={category.id}>
                    <td>
                      <strong>{category.name}</strong>
                      <small>{t('common.id')} {category.id}</small>
                    </td>
                    <td>{category.slug}</td>
                    <td>{category.description ?? t('common.notProvided')}</td>
                    <td>{formatDate(category.updated_at, language)}</td>
                    <td>
                      <div className="table-actions">
                        <button
                          className="text-button"
                          type="button"
                          onClick={() => selectCategory(category)}
                        >
                          {t('common.edit')}
                        </button>
                        <button
                          className="text-button danger-text"
                          type="button"
                          onClick={() => void deleteCategory(category)}
                        >
                          {t('common.delete')}
                        </button>
                      </div>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </section>

        <section className="panel">
          <div className="section-heading">
            <h2>{editingCategory ? t('taxonomy.editCategory') : t('taxonomy.createCategory')}</h2>
            {editingCategory ? (
              <button className="text-button" type="button" onClick={resetCategoryForm}>
                {t('common.new')}
              </button>
            ) : null}
          </div>
          <p className="muted-text">{t('taxonomy.slugHint')}</p>
          {categoryError ? <div className="form-error">{categoryError}</div> : null}
          <form className="form-stack taxonomy-form" onSubmit={submitCategory}>
            <label className="field">
              <span>{t('common.name')}</span>
              <input
                value={categoryForm.name}
                onChange={(event) => {
                  const name = event.target.value;
                  setCategoryForm((current) => ({
                    ...current,
                    name,
                    slug: current.slug && current.slug !== slugify(current.name) ? current.slug : slugify(name),
                  }));
                }}
              />
            </label>
            <label className="field">
              <span>{t('productEditor.slug')}</span>
              <input
                value={categoryForm.slug}
                onChange={(event) =>
                  setCategoryForm((current) => ({ ...current, slug: event.target.value }))
                }
              />
            </label>
            <label className="field">
              <span>{t('taxonomy.categoryDescription')}</span>
              <textarea
                rows={4}
                value={categoryForm.description}
                onChange={(event) =>
                  setCategoryForm((current) => ({ ...current, description: event.target.value }))
                }
              />
            </label>
            <button className="button button-primary" disabled={saving === 'category'} type="submit">
              {saving === 'category'
                ? t('common.saving')
                : editingCategory
                  ? t('common.save')
                  : t('taxonomy.createCategory')}
            </button>
          </form>
        </section>

        <section className="table-panel">
          <div className="section-heading table-heading">
            <div>
              <h2>{t('taxonomy.tagsTitle')}</h2>
              <p>{t('customerNotifications.rows', { count: tags.length })}</p>
            </div>
          </div>
          <table>
            <thead>
              <tr>
                <th>{t('common.name')}</th>
                <th>{t('productEditor.slug')}</th>
                <th>{t('common.updated')}</th>
                <th>{t('common.actions')}</th>
              </tr>
            </thead>
            <tbody>
              {tags.length === 0 ? (
                <tr>
                  <td colSpan={4}>
                    <div className="empty-table">{t('taxonomy.emptyTags')}</div>
                  </td>
                </tr>
              ) : (
                tags.map((tag) => (
                  <tr key={tag.id}>
                    <td>
                      <strong>{tag.name}</strong>
                      <small>{t('common.id')} {tag.id}</small>
                    </td>
                    <td>{tag.slug}</td>
                    <td>{formatDate(tag.updated_at, language)}</td>
                    <td>
                      <div className="table-actions">
                        <button className="text-button" type="button" onClick={() => selectTag(tag)}>
                          {t('common.edit')}
                        </button>
                        <button
                          className="text-button danger-text"
                          type="button"
                          onClick={() => void deleteTag(tag)}
                        >
                          {t('common.delete')}
                        </button>
                      </div>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </section>

        <section className="panel">
          <div className="section-heading">
            <h2>{editingTag ? t('taxonomy.editTag') : t('taxonomy.createTag')}</h2>
            {editingTag ? (
              <button className="text-button" type="button" onClick={resetTagForm}>
                {t('common.new')}
              </button>
            ) : null}
          </div>
          <p className="muted-text">{t('taxonomy.slugHint')}</p>
          {tagError ? <div className="form-error">{tagError}</div> : null}
          <form className="form-stack taxonomy-form" onSubmit={submitTag}>
            <label className="field">
              <span>{t('common.name')}</span>
              <input
                value={tagForm.name}
                onChange={(event) => {
                  const name = event.target.value;
                  setTagForm((current) => ({
                    ...current,
                    name,
                    slug: current.slug && current.slug !== slugify(current.name) ? current.slug : slugify(name),
                  }));
                }}
              />
            </label>
            <label className="field">
              <span>{t('productEditor.slug')}</span>
              <input
                value={tagForm.slug}
                onChange={(event) => setTagForm((current) => ({ ...current, slug: event.target.value }))}
              />
            </label>
            <button className="button button-primary" disabled={saving === 'tag'} type="submit">
              {saving === 'tag'
                ? t('common.saving')
                : editingTag
                  ? t('common.save')
                  : t('taxonomy.createTag')}
            </button>
          </form>
        </section>
      </div>
    </div>
  );
}
