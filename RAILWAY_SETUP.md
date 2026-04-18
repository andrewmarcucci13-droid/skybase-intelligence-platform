# Railway Deployment — Step-by-Step

## The Worker Healthcheck Problem

Railway applies `railway.json` to every service, including the worker.
The worker is a Celery process — it has **no HTTP server**, so Railway's healthcheck always fails.

**Fix:** In the worker service settings on Railway:
1. Click the **worker** service → **Settings** tab
2. Scroll to **Deploy** section → find **Healthcheck Path**
3. **Delete the path entirely** (leave it blank) to disable the healthcheck
4. Also override the **Start Command** to:
   ```
   celery -A app.tasks.orchestrator:celery_app worker --loglevel=info --concurrency=2
   ```
5. Click **Save** → Railway will redeploy automatically

---

## Environment Variables — Exact Values

### Critical: Fix These Wrong Values First

The following variables in your Railway worker (and web) service have **wrong placeholder values**
that will crash the app on startup:

| Variable | Wrong Value | Correct Value |
|---|---|---|
| `DATABASE_URL` | `postgresql://skybase:skybase@localhost:5432/skybase` | Must be Railway's internal Postgres URL — see below |
| `REDIS_URL` | `redis://localhost:6379/0` | Must be Railway's internal Redis URL — see below |
| `APP_ENV` | `development` | `production` |
| `FRONTEND_URL` | `http://localhost:3000` | `https://skybaseintel.com` |
| `SECRET_KEY` | `generate-a-random-32-char-string` | `0a5d263856badc969e7a016e51fcb318927e4d4e7411641cf62b317b966608b9` |

---

## How to Get DATABASE_URL and REDIS_URL from Railway

Railway generates these automatically from your managed services.

### DATABASE_URL
1. In your Railway project, click the **PostgreSQL** service
2. Click the **Variables** tab
3. Find `DATABASE_URL` — copy its value (looks like `postgresql://postgres:password@monorail.proxy.rlwy.net:PORT/railway`)
4. Go to your **web** service → Variables → paste it as `DATABASE_URL`
5. Do the same for the **worker** service

### REDIS_URL
1. Click the **Redis** service in your project
2. Click **Variables** tab
3. Find `REDIS_URL` — copy its value (looks like `redis://default:password@monorail.proxy.rlwy.net:PORT`)
4. Paste it as `REDIS_URL` in both the web and worker services

**Shortcut:** Instead of copy-pasting, use Railway's **Reference Variables**:
- In web/worker Variables tab, click **New Variable**
- Set key = `DATABASE_URL`, then in the value field click **Add Reference**
- Select the PostgreSQL service and pick `DATABASE_URL`
- This auto-updates if the connection string ever changes

---

## Complete Variable List for Web Service

```
DATABASE_URL         = (reference from PostgreSQL service)
REDIS_URL            = (reference from Redis service)
STRIPE_SECRET_KEY    = (your sk_test_... key from Stripe Dashboard)
STRIPE_PUBLISHABLE_KEY = (your pk_test_... key from Stripe Dashboard)
STRIPE_WEBHOOK_SECRET = (whsec_... from Stripe → Webhooks)
STRIPE_PRICE_ID      = price_1TNhCiB6nlyxBcZvphYPYmK5
STRIPE_SUB_PRICE_ID  = price_1TNhCiB6nlyxBcZvchN2Q9CA
APP_ENV              = production
FRONTEND_URL         = https://skybaseintel.com
SECRET_KEY           = 0a5d263856badc969e7a016e51fcb318927e4d4e7411641cf62b317b966608b9
FROM_EMAIL           = reports@skybaseintel.com
```

Leave these blank for now (optional — not required to run):
```
EIA_API_KEY          = (leave empty)
GOOGLE_MAPS_API_KEY  = (leave empty)
AWS_ACCESS_KEY_ID    = (leave empty)
AWS_SECRET_ACCESS_KEY = (leave empty)
AWS_S3_BUCKET        = skybase-reports
AWS_REGION           = us-east-1
```

## Complete Variable List for Worker Service

Same as web, plus the start command override:
```
DATABASE_URL         = (reference from PostgreSQL service — same as web)
REDIS_URL            = (reference from Redis service — same as web)
STRIPE_SECRET_KEY    = (same as web)
STRIPE_PRICE_ID      = price_1TNhCiB6nlyxBcZvphYPYmK5
APP_ENV              = production
SECRET_KEY           = 0a5d263856badc969e7a016e51fcb318927e4d4e7411641cf62b317b966608b9
```

---

## Step 4 — Add Stripe Webhook

1. Go to [dashboard.stripe.com/webhooks](https://dashboard.stripe.com/webhooks)
2. Click **Add endpoint**
3. URL: `https://<your-railway-domain>/api/v1/analyses/webhook/stripe`
   - Find your Railway domain under web service → **Settings** → **Networking** → **Public Networking**
4. Events: select `checkout.session.completed`
5. After saving, click **Reveal** on the signing secret → copy the `whsec_...` value
6. Paste it as `STRIPE_WEBHOOK_SECRET` in Railway web service variables

---

## Troubleshooting

**Worker crashes on startup:**
- Most likely `REDIS_URL` is still `redis://localhost:6379/0` — Celery can't connect to localhost inside Railway
- Fix: set `REDIS_URL` to the Railway Redis internal URL (see above)

**Web service 500 errors:**
- Most likely `DATABASE_URL` is still the localhost placeholder
- Fix: set it to the Railway PostgreSQL URL

**PDF reports not generating:**
- Worker needs the same `DATABASE_URL` and `REDIS_URL` as the web service
- Verify both variables are set on the worker service too
