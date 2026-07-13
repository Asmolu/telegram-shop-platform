# Roles and permissions

| API group | Public | `USER` | `SELLER` | `ADMIN` | Ownership / mutation |
| --- | --- | --- | --- | --- | --- |
| health/status | Read | Read | Read | Read | no business data |
| feed, public taxonomy, Looks, reviews | Read | Read | Read | Read | optional auth telemetry |
| products public | Read; OpenAPI may show optional bearer | Read | Read | Read | direct ACTIVE lookup |
| cart/favorites/profile | No | CRUD own | own if used | own if used | user id from JWT |
| orders/payment/returns customer | No | own read/create/cancel where allowed | own customer path only | same | service checks user/order link |
| catalog/taxonomy/banner/promo/Look admin | No | No | CRUD | CRUD | seller/admin dependency |
| orders/payments/returns admin | No | No | Read/mutate | Read/mutate | audit where implemented |
| reviews moderation | public approved only | create/read own | moderate | moderate | purchase required for create |
| campaigns/subscriptions reports | No | own subscription settings | manage | manage | marketing/service constraints |
| channel entry | No | No | manage | manage | Bot 1 configured channel |
| user blocks/audit/outbox | No | No | restricted/No depending endpoint | manage/read | admin intent; verify router dependency |
| uploads | status public | return/payment scoped endpoints | content uploads | content uploads | file profile + linked entity |

Authentication uses Bearer JWT; inactive user is rejected. `require_roles` enforces coarse RBAC;
services/repositories enforce ownership. Seller Bot callbacks additionally require recognized
Telegram identity, allowed role and configured operational chat.

Source: `backend/app/common/deps.py`, all `backend/app/modules/*/router.py` and services.

**NEEDS VERIFICATION**: a formal policy decision on whether every analytics/audit endpoint should be
ADMIN-only is not stored outside code. Security owner must approve the generated matrix before a
third-party security review. This blocks compliance claims, not current operation.

