import React from 'react';
import {
  getProductSearchSuggestions,
  type ProductSearchSuggestion,
} from '../../shared/api';
import { SearchIcon } from '../../shared/ui';

const MIN_SUGGESTION_QUERY_LENGTH = 2;
const SUGGESTION_DEBOUNCE_MS = 280;

const SUGGESTION_KIND_LABELS: Record<ProductSearchSuggestion['kind'], string> = {
  product: 'Товар',
  brand: 'Бренд',
  alias: 'Запрос',
  category: 'Категория',
  tag: 'Подборка',
};

type SearchAutocompleteProps = {
  value: string;
  onChange: (value: string) => void;
  onSearch: (value: string) => void;
  placeholder: string;
  submitLabel: string;
  submitAriaLabel?: string;
  className?: string;
};

export function SearchAutocomplete({
  value,
  onChange,
  onSearch,
  placeholder,
  submitLabel,
  submitAriaLabel,
  className,
}: SearchAutocompleteProps) {
  const listId = React.useId();
  const [suggestions, setSuggestions] = React.useState<ProductSearchSuggestion[]>([]);
  const [loading, setLoading] = React.useState(false);
  const [focused, setFocused] = React.useState(false);
  const [activeIndex, setActiveIndex] = React.useState(-1);
  const trimmedValue = value.trim();
  const suggestionsVisible = focused
    && trimmedValue.length >= MIN_SUGGESTION_QUERY_LENGTH
    && (loading || suggestions.length > 0);
  const activeDescendant = activeIndex >= 0
    ? `${listId}-option-${activeIndex}`
    : undefined;

  React.useEffect(() => {
    setActiveIndex(-1);
  }, [value]);

  React.useEffect(() => {
    let cancelled = false;

    if (trimmedValue.length < MIN_SUGGESTION_QUERY_LENGTH) {
      setSuggestions([]);
      setLoading(false);
      return () => {
        cancelled = true;
      };
    }

    const controller = new AbortController();
    setSuggestions([]);
    setLoading(true);
    const timeoutId = window.setTimeout(() => {
      getProductSearchSuggestions(trimmedValue, 8, { signal: controller.signal, dedupe: false })
        .then((result) => {
          if (!cancelled) {
            setSuggestions(result.items);
          }
        })
        .catch(() => {
          if (!cancelled) {
            setSuggestions([]);
          }
        })
        .finally(() => {
          if (!cancelled) {
            setLoading(false);
          }
        });
    }, SUGGESTION_DEBOUNCE_MS);

    return () => {
      cancelled = true;
      controller.abort();
      window.clearTimeout(timeoutId);
    };
  }, [trimmedValue]);

  function chooseSuggestion(suggestion: ProductSearchSuggestion) {
    onChange(suggestion.value);
    setFocused(false);
    setActiveIndex(-1);
    onSearch(suggestion.value);
  }

  function handleKeyDown(event: React.KeyboardEvent<HTMLInputElement>) {
    if (event.key === 'Escape') {
      setFocused(false);
      setActiveIndex(-1);
      return;
    }

    if (!suggestionsVisible || suggestions.length === 0) {
      return;
    }

    if (event.key === 'ArrowDown') {
      event.preventDefault();
      setActiveIndex((current) => (current + 1) % suggestions.length);
      return;
    }

    if (event.key === 'ArrowUp') {
      event.preventDefault();
      setActiveIndex((current) => (
        current <= 0 ? suggestions.length - 1 : current - 1
      ));
      return;
    }

    if (event.key === 'Enter' && activeIndex >= 0) {
      event.preventDefault();
      chooseSuggestion(suggestions[activeIndex]);
    }
  }

  function handleBlur(event: React.FocusEvent<HTMLDivElement>) {
    if (!event.currentTarget.contains(event.relatedTarget as Node | null)) {
      setFocused(false);
      setActiveIndex(-1);
    }
  }

  return (
    <div className={`search-autocomplete search-row ${className ?? ''}`.trim()} onBlur={handleBlur}>
      <label className="search-field search-field--input">
        <SearchIcon className="search-icon" />
        <input
          value={value}
          onChange={(event) => onChange(event.target.value)}
          onFocus={() => setFocused(true)}
          onKeyDown={handleKeyDown}
          placeholder={placeholder}
          type="search"
          aria-autocomplete="list"
          aria-controls={listId}
          aria-expanded={suggestionsVisible}
          aria-activedescendant={activeDescendant}
        />
      </label>
      <button className="search-submit-button" type="submit" aria-label={submitAriaLabel}>
        {submitLabel}
      </button>

      {suggestionsVisible ? (
        <div className="search-suggestions" id={listId} role="listbox">
          {loading ? (
            <div className="search-suggestions__status" role="status">
              Ищем...
            </div>
          ) : null}
          {suggestions.map((suggestion, index) => (
            <button
              className={`search-suggestion ${activeIndex === index ? 'is-active' : ''}`}
              id={`${listId}-option-${index}`}
              key={`${suggestion.kind}-${suggestion.value}`}
              type="button"
              role="option"
              aria-selected={activeIndex === index}
              onMouseDown={(event) => event.preventDefault()}
              onClick={() => chooseSuggestion(suggestion)}
            >
              <span className="search-suggestion__text">{suggestion.value}</span>
              <span className="search-suggestion__kind">
                {suggestion.label ?? SUGGESTION_KIND_LABELS[suggestion.kind]}
              </span>
            </button>
          ))}
        </div>
      ) : null}
    </div>
  );
}
