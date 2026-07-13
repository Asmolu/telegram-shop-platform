# Reviews and favorites

## Reviews

Authenticated customer may review a product only after purchase: repository verifies an OrderItem in
the customer’s order. User/product pair is unique. New review is `PENDING`; seller/admin moderates to
`APPROVED` or `REJECTED`. Public product endpoint returns only approved reviews. Seller Panel provides
moderation. Raw enums must be localized in customer UI.

Source: `reviews/service.py`, `reviews/repository.py`, model `Review`, tests `test_reviews.py`.

## Favorites

Authenticated customer can list own favorites, add a product and delete by product id. Unique
`(user_id, product_id)` prevents duplicates; ownership comes from JWT user id. Favorites are not public
and do not change product visibility/stock.

Source: `favorites/router.py`, `favorites/service.py`, model `Favorite`.

