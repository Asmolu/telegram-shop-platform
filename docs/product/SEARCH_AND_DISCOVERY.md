# Search and discovery

Public product search considers name, slug, brand, description, aliases, legacy/current categories
and tags. Text is sanitized, case-folded and normalizes `ё` to `е`; color synonyms are expanded.
PostgreSQL `similarity()` via `pg_trgm` supports typo tolerance with threshold defined in
`products/search.py`. Application helpers also use normalized Levenshtein similarity for suggestions.

Ranking: when search exists, lower `search_priority` first, then category assignment priority where
applicable, then newest/id. Filters include category, tag, size grid, size and color. Suggestions
combine product, brand, category, tag and alias candidates.

Only ACTIVE/listed products appear in lists/search/suggestions/similar. Similar products require
category/tag overlap and rank direct configuration/category/tags. Hidden product direct ACTIVE detail
remains accessible; hidden product can appear only as component within a public Look, not as similar card.

RouteAlias resolves previous Product/Category/Look slugs and redirects UI to canonical path. SKU alias
history is not implemented.

Source: `products/search.py`, `products/repository.py`, `products/service.py`,
`route_aliases/service.py`, migration `20260608_0020`.

