import React from 'react';
import { getCategories, getTags, toApiErrorMessage, type Category, type Tag } from '../shared/api';
import { useRouter } from '../shared/router/RouterProvider';
import { ErrorState, PageLoader, TopBar } from '../shared/ui';

export function SearchPage() {
  const { navigate } = useRouter();
  const [categories, setCategories] = React.useState<Category[]>([]);
  const [tags, setTags] = React.useState<Tag[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);
  const [query, setQuery] = React.useState('');
  const [categoryId, setCategoryId] = React.useState('');
  const [tagId, setTagId] = React.useState('');
  const [size, setSize] = React.useState('');
  const [color, setColor] = React.useState('');
  const [priceFrom, setPriceFrom] = React.useState('');
  const [priceTo, setPriceTo] = React.useState('');
  const [sort, setSort] = React.useState('');

  React.useEffect(() => {
    let cancelled = false;
    async function load() {
      setLoading(true);
      setError(null);
      try {
        const [categoryResult, tagResult] = await Promise.all([getCategories(), getTags()]);
        if (!cancelled) {
          setCategories(categoryResult);
          setTags(tagResult);
        }
      } catch (loadError) {
        if (!cancelled) {
          setError(toApiErrorMessage(loadError));
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    void load();
    return () => {
      cancelled = true;
    };
  }, []);

  function showProducts(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const params = new URLSearchParams();
    if (query.trim()) params.set('q', query.trim());
    if (categoryId) params.set('category_id', categoryId);
    if (tagId) params.set('tag_id', tagId);
    if (size.trim()) params.set('size', size.trim());
    if (color.trim()) params.set('color', color.trim());
    if (priceFrom) params.set('price_from', priceFrom);
    if (priceTo) params.set('price_to', priceTo);
    if (sort) params.set('sort', sort);
    navigate(`/search/results?${params.toString()}`);
  }

  return (
    <div className="page">
      <TopBar title="Поиск товаров" variant="marketplace" />
      {loading ? <PageLoader text="Готовим фильтры..." /> : null}
      {!loading && error ? <ErrorState message={error} /> : null}
      {!loading && !error ? (
        <form className="filter-form filter-form--compact" onSubmit={showProducts}>
          <label className="input-shell">
            <span>⌕</span>
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Найти одежду, бренд, размер..."
              type="search"
            />
          </label>

          <section className="filter-section">
            <h2>Категория</h2>
            <select value={categoryId} onChange={(event) => setCategoryId(event.target.value)}>
              <option value="">Все категории</option>
              {categories.map((category) => (
                <option value={category.id} key={category.id}>
                  {category.name}
                </option>
              ))}
            </select>
          </section>

          <section className="filter-section filter-section--secondary">
            <h2>Размер</h2>
            <div className="chip-row">
              {['XS', 'S', 'M', 'L', 'XL', 'XXL'].map((item) => (
                <button
                  className={size === item ? 'is-selected' : ''}
                  key={item}
                  type="button"
                  onClick={() => setSize(size === item ? '' : item)}
                >
                  {item}
                </button>
              ))}
            </div>
          </section>

          <section className="filter-section filter-section--secondary">
            <h2>Бюджет</h2>
            <div className="two-inputs">
              <input value={priceFrom} onChange={(event) => setPriceFrom(event.target.value)} placeholder="от" type="number" min="0" />
              <input value={priceTo} onChange={(event) => setPriceTo(event.target.value)} placeholder="до" type="number" min="0" />
            </div>
          </section>

          <section className="filter-section filter-section--secondary">
            <h2>Цвет</h2>
            <input
              value={color}
              onChange={(event) => setColor(event.target.value)}
              placeholder="Например: черный"
            />
          </section>

          <section className="filter-section filter-section--secondary">
            <h2>Подборки</h2>
            <div className="chip-row">
              {tags.map((tag) => (
                <button
                  className={tagId === String(tag.id) ? 'is-selected' : ''}
                  key={tag.id}
                  type="button"
                  onClick={() => setTagId(tagId === String(tag.id) ? '' : String(tag.id))}
                >
                  {tag.name}
                </button>
              ))}
            </div>
          </section>

          <section className="filter-section filter-section--secondary">
            <h2>Сортировка</h2>
            <div className="segmented-control">
              {[
                ['', 'По умолчанию'],
                ['newest', 'Новинки'],
                ['price_asc', 'Сначала дешевле'],
                ['price_desc', 'Сначала дороже'],
              ].map(([value, label]) => (
                <button
                  className={sort === value ? 'is-selected' : ''}
                  key={value}
                  type="button"
                  onClick={() => setSort(value)}
                >
                  {label}
                </button>
              ))}
            </div>
          </section>

          <button className="sticky-submit-button" type="submit">
            Найти товары
          </button>
        </form>
      ) : null}
    </div>
  );
}
