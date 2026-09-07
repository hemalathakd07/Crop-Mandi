# CropMandi AI V1 — Coffee + Pepper backend

Cardamom is out of scope for V1 market data. The dashboard includes a Razorpay **TEST MODE** demo checkout; it is not a live crop sale.

## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
copy .env.example .env
```

If Docker/Postgres is unavailable, set in `.env`:

```
DATABASE_URL=sqlite:///./data/cropmandi.db
```

SQLite is a local fallback only.

## Ingest (production Pepper / Coffee Board PDFs)

```powershell
.\.venv\Scripts\alembic upgrade head
.\.venv\Scripts\python -m ingest.audit_datasets
.\.venv\Scripts\python -m ingest.run
.\.venv\Scripts\python -m ingest.readiness
```

The unverified file `karnataka_daily_coffee_prices_7years.xlsx` is **not** inserted into `price_observations`. Experimental Coffee weekday frames live under `data/experimental/`.

## Experimental models (do not re-run for the API)

```powershell
.\.venv\Scripts\python -m ml
```

Phase 2 result: **RandomForestRegressor did not beat naive last-value** on any Coffee or Pepper series. The API uses `naive_last_value` as a **baseline estimate**, not an ML forecast. Saved metrics: `ml/experiments/`.

## API

The dashboard JavaScript calls `http://127.0.0.1:8001`. Start the API on that port:

```powershell
.\.venv\Scripts\uvicorn apps.api.main:app --reload --host 127.0.0.1 --port 8001
.\.venv\Scripts\python.exe -m pytest -q
```

OpenAPI: `http://127.0.0.1:8001/docs`

## Razorpay TEST MODE payments

Do not put live keys or any secret values in git, README, or frontend JavaScript. The Key Secret and webhook secret stay on the server only.

1. Create a Razorpay account and switch the dashboard to **Test Mode**.
2. Generate Test API keys (`rzp_test_...` Key ID plus Key Secret).
3. Copy `.env.example` to `.env` if needed, then set:

```
RAZORPAY_KEY_ID=rzp_test_your_key_id
RAZORPAY_KEY_SECRET=
RAZORPAY_WEBHOOK_SECRET=
```

4. Webhooks cannot reach localhost directly. Use a tunnel (for example ngrok) or a staging HTTPS URL, then in Razorpay Dashboard → Webhooks add:

`https://<your-public-host>/api/payment/webhook`

Recommended events: `payment.authorized`, `payment.captured`, `payment.failed`, `order.paid`.
Paste the webhook secret into `RAZORPAY_WEBHOOK_SECRET`. Never disable signature verification.

5. Start the backend on port 8001 (command above).
6. Open the dashboard HTML (`frontend/cropmandi_ai_dashboard/code.html`) via a local static server such as `http://127.0.0.1:5500`.
7. Click **Pay ₹100 (Test Mode)**.
8. Razorpay Checkout should open. Complete a test payment with Razorpay test cards.
9. The UI shows success only after `POST /api/payment/verify` confirms the HMAC signature.
10. Confirm `GET /api/payment/status/<order_id>` returns `CAPTURED` (or `AUTHORIZED`).
11. If the tunnel is configured, Razorpay will also POST the webhook; duplicate deliveries are ignored.

Payment API:

| Method | Path | Notes |
|---|---|---|
| POST | `/api/payment/create-order` | Server sets ₹100 (10000 paise). Client amount is not trusted. |
| POST | `/api/payment/verify` | HMAC-SHA256 of `order_id|payment_id` using the server secret. |
| GET | `/api/payment/status/{order_id}` | Server-side status for the demo identity. |
| GET | `/api/payment/history` | Demo-identity history only. |
| POST | `/api/payment/cancel` | Marks `CREATED` orders cancelled after Checkout dismiss. |
| POST | `/api/payment/webhook` | Raw-body webhook signature check. Idempotent by event id. |

Local webhook checks (keep verification on): valid signature, invalid signature, duplicate event, malformed JSON, unknown event.

If Checkout does not open: confirm the API is on **8001**, browser console has no CORS/network error, `https://checkout.razorpay.com/v1/checkout.js` loaded, and `.env` test keys are present. Restart uvicorn after changing `.env`.

### Endpoints

| Method | Path | Query |
|---|---|---|
| GET | `/api/prices/latest` | `commodity=coffee\|pepper` |
| GET | `/api/prices/history` | `commodity`, `series` (required), optional `from`, `to` (`YYYY-MM-DD`) |
| GET | `/api/predictions/next` | `commodity`, `series` (required) |

Supported series:

- Coffee: `Arabica Parchment`, `Arabica Cherry`, `Robusta Parchment`, `Robusta Cherry`
- Pepper: `Cochin Garbled`, `Cochin Ungarbled`, `Sirsi`

`latest` is the last **observed** price. `predictions/next` is a **next-session estimate** equal to that last price (`naive_last_value`). It is not a trained-model forecast.

### Data status

- Coffee workbook responses: `data_status=UNVERIFIED_HISTORICAL_COFFEE_DATA`, `data_usage=EXPERIMENTAL_ONLY`, `official=false`. Not Coffee Board / official mandi data.
- Pepper: Spices Board `indicative_daily_average`. Not a guaranteed transaction price. Cochin and Sirsi are not mixed.

### Example: latest Coffee

`GET /api/prices/latest?commodity=coffee`

```json
{
  "available": true,
  "commodity": "coffee",
  "observations": [
    {
      "commodity": "coffee",
      "series": "Arabica Parchment",
      "price": 24000.0,
      "unit": "INR_PER_50KG",
      "observation_date": "2026-08-31",
      "official": false,
      "experimental": true,
      "data_status": "UNVERIFIED_HISTORICAL_COFFEE_DATA",
      "data_usage": "EXPERIMENTAL_ONLY"
    }
  ]
}
```

### Example: latest Pepper

`GET /api/prices/latest?commodity=pepper`

```json
{
  "available": true,
  "commodity": "pepper",
  "observations": [
    {
      "commodity": "pepper",
      "series": "Cochin Garbled",
      "price": 722.0,
      "unit": "INR_PER_KG",
      "price_type": "indicative_daily_average",
      "indicative": true,
      "guaranteed_transaction_price": false,
      "observation_date": "2026-09-03"
    }
  ]
}
```

### Example: next-session estimate (Coffee)

`GET /api/predictions/next?commodity=coffee&series=Arabica%20Parchment`

Coffee target session = next weekday (Friday → Monday). Pepper `target_session` is `null` because the next published date is unknown.

### Errors

| Situation | Status | `error` |
|---|---|---|
| Unsupported commodity | 400 | `unsupported_commodity` |
| Missing series | 400 | `missing_series_parameter` |
| Unsupported series | 400 | `unsupported_series` |
| Bad `from`/`to` | 400 | `invalid_date_filter` |
| No observations | 404 | `no_available_observations` |

Stack traces are not returned to clients.
