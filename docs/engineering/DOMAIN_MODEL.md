# Domain model

Core aggregates:

- **Identity**: User, SellerCredential, PendingSellerRegistration, UserBlock.
- **Catalog**: Product, ProductVariant, ProductImage, Category, Tag, ProductCategory, RouteAlias.
- **Commerce**: Cart/CartItem, Order/OrderItem, PromoCode/CouponUsage, ManualPayment.
- **Post-purchase**: Review, Favorite, ReturnRequest/Item/Attachment/Refund.
- **Merchandising**: Look/LookItem/LookImage, Banner.
- **Communication**: CustomerTelegramSubscription, Notification, templates/campaigns/deliveries,
  CustomerInAppNotification, TelegramChannel/EntryMessage.
- **Reliability/governance**: IdempotencyRecord, OutboxEvent/Delivery, AnalyticsEvent, AuditLog.

Order is aggregate root for purchased snapshots/payment/return. ProductVariant is locked during
checkout/restock. User owns cart/order/favorites/reviews/returns and notification state.

Source: `backend/app/db/models.py`.

