# Looks

A Look is an independent outfit entity with title/slug/description/status/listing/priority/images,
badge settings and ordered `LookItem` product components. It has no stock; availability is derived
from active ProductVariants at request/cart time. Duplicate product in one Look is forbidden.

## Publish and visibility

Look status enum: `DRAFT`, `ACTIVE`, `ARCHIVED`. Product size groups: `CLOTHING`, `FOOTWEAR`, `ONE_SIZE`.

ACTIVE Look must contain at least one stored `is_default_selected=true` component and only ACTIVE,
non-archived products. Hidden ACTIVE products are allowed. A public Look itself must be ACTIVE and
`is_listed=true`; unlike Product direct detail, hidden Look is not publicly resolvable.

## Size behavior

| Selected composition | UI / API behavior |
| --- | --- |
| Clothing only | one clothing carousel from intersection of available sizes |
| Footwear only | one footwear carousel |
| Clothing + footwear | independent carousels; both required |
| ONE_SIZE + sized | ONE_SIZE auto-resolves and does not block sized selector |
| ONE_SIZE only | no carousel; variant auto-resolves |

`ONE_SIZE` is intended for accessory-like components, but code does not enforce a category. Stockless
or inactive variant makes component/cart action unavailable. All cart additions are grouped with a
new `source_group_id` and snapshot Look identity into cart/order items.

## Current default-selection truth

Seller Panel stores `is_default_selected`; ACTIVE requires at least one. However
`LooksService._build_card/_build_detail` currently returns every item id in
`default_selected_item_ids`, and Mini App `getInitialSelectedItemIds` selects all items. Therefore
«configured defaults determine initial customer selection» is **Partial**, not production-ready.

## Image badges

Types: `none`, `new`, `sale`, `hit`, `exclusive`, `custom`; colors: purple, pink, red, orange,
blue, green, black, white; positions: four corners. Custom requires text. Product and Look editor
use shared Seller Panel configurator.

Source: `looks/service.py`, `looks/repository.py`, `db/models.py`,
`mini-app/src/pages/LookDetailPage.tsx`, `seller-panel/src/shared/ui/ImageBadgeConfigurator.tsx`.
