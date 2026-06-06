# Deploying Vizion

Production stack: **Supabase** (auth + DB + video storage) · **Railway** (backend + Manim) · **Vercel** (frontend)

Estimated cost to start: **$0–20/mo** (Supabase/Groq/Vercel free tiers + Railway ~$5+)

---

## Prerequisites

- GitHub repo pushed with this code
- Accounts: [Supabase](https://supabase.com), [Railway](https://railway.app), [Vercel](https://vercel.com), [Groq](https://console.groq.com)
- Optional: [Stripe](https://stripe.com) for Pro billing

---

## Step 1 — Supabase (production)

### 1.1 Create project

1. Go to [supabase.com/dashboard](https://supabase.com/dashboard) → **New project**
2. Save your database password

### 1.2 Run database setup

**Option A — SQL Editor (easiest)**

1. Open **SQL Editor** in Supabase Dashboard
2. Paste and run the entire file: [`supabase/production_setup.sql`](supabase/production_setup.sql)

**Option B — CLI**

```bash
npm i -g supabase
supabase login
supabase link --project-ref YOUR_PROJECT_REF
supabase db push
```

### 1.3 Verify storage bucket

In **Storage**, confirm a public bucket named **`videos`** exists.

### 1.4 Copy API keys

**Project Settings → API**:

| Variable | Where to use |
|----------|--------------|
| `SUPABASE_URL` | Railway backend |
| `SUPABASE_ANON_KEY` | Railway backend |
| `SUPABASE_SERVICE_KEY` | Railway backend only (secret) |

### 1.5 Auth URLs (after you have Vercel URL)

**Authentication → URL Configuration**:

- **Site URL:** `https://YOUR_APP.vercel.app`
- **Redirect URLs:** `https://YOUR_APP.vercel.app/login`

---

## Step 2 — Backend on Railway

### 2.1 Create service

1. [railway.app/new](https://railway.app/new) → **Deploy from GitHub repo**
2. Select this repository
3. Railway reads [`railway.toml`](railway.toml) and builds with [`Dockerfile`](Dockerfile)

### 2.2 Set environment variables

In Railway → your service → **Variables**, add (see [`env.example`](env.example)):

```env
ENV=production

SUPABASE_URL=https://xxxx.supabase.co
SUPABASE_ANON_KEY=eyJ...
SUPABASE_SERVICE_KEY=eyJ...

LLM_PROVIDER=groq
GROQ_API_KEY=gsk_...
GROQ_MODEL=qwen/qwen3-32b

FRONTEND_URL=https://YOUR_APP.vercel.app

STRIPE_SECRET_KEY=sk_test_...
STRIPE_WEBHOOK_SECRET=whsec_...
STRIPE_PRICE_ID=price_...
```

> First deploy takes ~5–10 min (Manim + LaTeX + ML model download).

### 2.3 Get backend URL

Railway → **Settings → Networking → Generate domain**

Example: `https://vizion-api-production.up.railway.app`

Test: open `https://YOUR_RAILWAY_URL/docs`

### 2.4 Resources

- **Memory:** at least **2 GB** recommended (Manim renders)
- **Timeout:** video generation can take 1–5 minutes; Railway HTTP timeout may need a paid plan for long requests

---

## Step 3 — Frontend on Vercel

### 3.1 Import project

1. [vercel.com/new](https://vercel.com/new) → Import GitHub repo
2. **Root Directory:** `vizion-ui`
3. **Framework Preset:** Vite
4. **Build Command:** `npm run build`
5. **Output Directory:** `dist`

### 3.2 Environment variable

| Name | Value |
|------|-------|
| `VITE_API_URL` | `https://YOUR_RAILWAY_URL` (no trailing slash) |

See [`vizion-ui/.env.production.example`](vizion-ui/.env.production.example).

### 3.3 Deploy

Vercel uses [`vizion-ui/vercel.json`](vizion-ui/vercel.json) for SPA routing.

Copy your Vercel URL (e.g. `https://vizion.vercel.app`) and update:

- Railway `FRONTEND_URL`
- Supabase Auth Site URL + Redirect URLs

Redeploy Railway after changing `FRONTEND_URL`.

---

## Step 4 — Stripe webhook (optional)

1. Stripe Dashboard → **Developers → Webhooks → Add endpoint**
2. **URL:** `https://YOUR_RAILWAY_URL/billing/webhook`
3. **Event:** `checkout.session.completed`
4. Copy signing secret → Railway `STRIPE_WEBHOOK_SECRET`

Use test card `4242 4242 4242 4242` before going live.

---

## Step 5 — Smoke test

1. Open your Vercel URL
2. Sign up with a Gmail address
3. Prompt: **"Draw a blue circle"**
4. Wait 1–3 minutes for generation
5. Video should play in the preview panel
6. Check Supabase **Storage → videos** for uploaded MP4

---

## Local development

```bash
# Backend
cp env.example .env   # fill in keys
source venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload

# Frontend (separate terminal)
cd vizion-ui
npm install
npm run dev
```

Frontend defaults to `http://localhost:8000` when `VITE_API_URL` is unset.

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| CORS error in browser | Set Railway `FRONTEND_URL` to exact Vercel URL, `ENV=production`, redeploy |
| `Invalid token` after deploy | Log out and sign up again on production Supabase |
| `Could not find table chats` | Run `supabase/production_setup.sql` |
| NetworkError / timeout | Railway plan may timeout long Manim renders; try simpler prompt first |
| Video upload fails | Confirm `videos` bucket exists and `SUPABASE_SERVICE_KEY` is set |

---

## Architecture

```
User → Vercel (React) → Railway (FastAPI + Manim)
                              ↓
                         Supabase (auth, chats, video storage)
                              ↓
                         Groq (LLM script generation)
```

---

## Files added for deployment

| File | Purpose |
|------|---------|
| `Dockerfile` | Backend image with Manim + LaTeX |
| `railway.toml` | Railway build config |
| `vizion-ui/vercel.json` | SPA routing on Vercel |
| `env.example` | Backend env template |
| `vizion-ui/.env.production.example` | Frontend env template |
| `vizion-ui/src/lib/api/config.ts` | `VITE_API_URL` helper |
| `supabase/production_setup.sql` | One-shot production DB setup |
