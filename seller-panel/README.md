# Telegram Shop Seller Panel

React + Vite + TypeScript frontend placeholder.

## Run

```bash
npm install
npm run dev
```

## Environment

Create local env file:

```bash
cp .env.example .env
```

Windows PowerShell:

```powershell
Copy-Item .env.example .env
```

## API

The frontend should call the FastAPI backend through:

```text
VITE_API_BASE_URL
```

Seller auth uses `/seller-auth/login` and `/seller-auth/register/*`.
Registration shows the Bot 2 `/start seller_<token>` command returned by the
backend; the Telegram bot token stays backend-only.
