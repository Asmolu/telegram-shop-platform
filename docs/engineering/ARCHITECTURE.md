# Архитектура

TelegramShopPlatform — modular monolith: один FastAPI process/API и два React applications,
PostgreSQL source of truth, Redis auxiliary state, Telegram integrations и background workers.

```mermaid
flowchart TB
  subgraph Clients
    TG["Telegram"] --> MA["Mini App"]
    BR["Browser"] --> MA
    SP["Seller Panel"]
    B2["Bot 2 seller/admin"]
  end
  RP["Host reverse proxy / TLS"]
  MA --> RP
  SP --> RP
  B2 --> RP
  RP --> API["FastAPI backend"]
  API --> PG[("PostgreSQL")]
  API --> RD[("Redis")]
  API --> UP["Uploads volume"]
  API --> B1["Bot 1 / Telegram API"]
  API --> B2
  SYS["systemd backup"] --> PG
  SYS --> UP
```

Production Compose: backend, mini-app, seller-panel, PostgreSQL 16, Redis 7. Host proxy is not
defined as a Compose service in current file. API workers run in backend lifespan, so horizontal
scaling requires explicit worker/concurrency review.

Sources: `backend/app/main.py`, `backend/app/api/router.py`, `docker-compose.prod.yml`.

