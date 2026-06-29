# Backend Jobs

Background jobs are currently started from the FastAPI lifespan inside the backend service.

## Current Workers

| Worker | Purpose | Settings |
| --- | --- | --- |
| Customer campaign worker | Processes scheduled/active customer campaign delivery batches | `CUSTOMER_CAMPAIGN_WORKER_ENABLED`, `CUSTOMER_CAMPAIGN_WORKER_POLL_SECONDS` |
| Manual payment expiration worker | Expires manual payments according to configured deadlines | `MANUAL_PAYMENT_EXPIRATION_WORKER_ENABLED`, `MANUAL_PAYMENT_EXPIRATION_POLL_SECONDS` |

## Customer Campaign Worker

The campaign worker sends through Bot 1 and uses campaign delivery rows. Eligibility requires real private Bot 1 chat state and the required service or marketing opt-in for the campaign type.

Related settings:

- `CUSTOMER_CAMPAIGN_BATCH_SIZE`
- `CUSTOMER_CAMPAIGN_MAX_ATTEMPTS`
- `CUSTOMER_CAMPAIGN_RETRY_BASE_SECONDS`
- `CUSTOMER_CAMPAIGN_WORKER_ENABLED`
- `CUSTOMER_CAMPAIGN_WORKER_POLL_SECONDS`
- `CUSTOMER_CAMPAIGN_SENDING_TIMEOUT_SECONDS`

## Manual Payment Expiration Worker

The manual payment expiration worker runs inside the backend process and checks for payments that should expire.

Related settings:

- `MANUAL_PAYMENT_EXPIRATION_WORKER_ENABLED`
- `MANUAL_PAYMENT_EXPIRATION_POLL_SECONDS`

## Production Logs

```bash
cd /opt/telegram-shop
docker compose --env-file backend/.env.production -f docker-compose.prod.yml logs --tail=200 backend
```

## Notes

- Workers run in the backend container in the current production stack.
- Do not add a separate worker runtime without updating deployment docs, compose files, and operations docs.
- Do not print bot tokens, customer payloads, or raw production env values in worker logs.
