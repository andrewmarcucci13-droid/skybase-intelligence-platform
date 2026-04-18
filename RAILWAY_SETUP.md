# Railway Deployment — Step-by-Step

Railway does not support multi-process Procfiles like Heroku. You need **three services**:
1. `web` — FastAPI (uses Dockerfile, starts uvicorn)
2. `worker` — Celery (uses same Dockerfile, overrides start command)
3. `postgres` — Railway managed PostgreSQL
4. `redis` — Railway managed Redis

---

## Step 1 — Create Project & Add Services

1. Go to [railway.app](https://railway.app) → **New Project**
2. Click **Add a Service** → **GitHub Repo** → select `skybase-intelligence-platform`
   - This becomes your **web** service
3. Click **Add a Service** → **GitHub Repo** → select `skybase-intelligence-platform` again
   - This becomes your **worker** service
4. Click **Add a Service** → **Database** → **PostgreSQL**
5. Click **Add a Service** → **Database** → **Redis**

---

## Step 2 — Configure Web Service

In the **web** service settings:
- **Build**: Dockerfile (auto-detected from `railway.json`)
- **Start Command**: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
- Add these environment variables (click Variables):

```
DATABASE_URL         → click "Add Reference" → select PostgreSQL → DATABASE_URL
REDIS_URL            → click "Add Reference" → select Redis → REDIS_URL
STRIPE_SECRET_KEY    = sk_test_...  (copy from Stripe Dashboard → Developers → API Keys)
STRIPE_WEBHOOK_SECRET = (get from Stripe dashboard after adding webhook — see Step 4)
STRIPE_PRICE_ID      = price_1TNhCiB6nlyxBcZvphYPYmK5
STRIPE_SUB_PRICE_ID  = price_1TNhCiB6nlyxBcZvchN2Q9CA
FRONTEND_URL         = https://skybaseintel.com
APP_ENV              = production
SECRET_KEY           = (generate a random string — e.g. openssl rand -hex 32)
```

- Under **Networking** → **Public Networking**: add domain `api.skybaseintel.com`

---

## Step 3 — Configure Worker Service

In the **worker** service settings:
- **Build**: Dockerfile (same image — Railway builds it once)
- **Start Command** (OVERRIDE): `celery -A app.tasks.orchestrator:celery_app worker --loglevel=info --concurrency=2`
  - To override: Settings → Deploy → Start Command → toggle off "Use Dockerfile CMD" → paste command
- Add the **same environment variables** as the web service (reference the same Postgres + Redis)
- **Do NOT** add a public domain to the worker — it doesn't need one

---

## Step 4 — Add Stripe Webhook

1. Go to [dashboard.stripe.com/webhooks](https://dashboard.stripe.com/webhooks)
2. Click **Add endpoint**
3. Endpoint URL: `https://api.skybaseintel.com/api/v1/analyses/webhook/stripe`
4. Events to listen for: `checkout.session.completed`
5. Click **Add endpoint**
6. On the next page, click **Reveal** under "Signing secret"
7. Copy the `whsec_...` value → paste as `STRIPE_WEBHOOK_SECRET` in Railway web service variables

---

## Step 5 — Deploy

1. Railway auto-deploys when you push to GitHub
2. Check **Deployments** tab for build logs
3. Web service should show green health check at `/health`
4. Worker service logs should show: `celery@... ready.`

---

## Troubleshooting

**Build fails:**
- Check Dockerfile — WeasyPrint needs system libs (libpango, libcairo) which are in the Dockerfile
- Make sure all requirements.txt packages are spelled correctly

**Worker not processing jobs:**
- Verify `REDIS_URL` is the same in both web and worker services
- Check worker logs for connection errors

**PDF not generating:**
- WeasyPrint on Railway may need additional fonts — if reports show blank text, add `fonts-liberation` to apt-get in Dockerfile

**`DATABASE_URL` format:**
- Railway gives you `postgresql://user:pass@host:port/db`
- SQLAlchemy works with this format directly — no changes needed
