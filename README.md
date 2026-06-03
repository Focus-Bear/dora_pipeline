# DORA Pipeline

A GitHub Actions-powered DORA metrics dashboard for Focus Bear, deployed to **Cloudflare Pages** with data stored in **Cloudflare R2**.

## Architecture

```
GitHub Actions cron (daily at 12:00 UTC)
  → Python scripts generate: dora.json, dora.sqlite, repo_summary*.csv
  → Upload data files to Cloudflare R2 (PRIVATE bucket — no public access)
  → Vite build (fetches data from /api/data/* at runtime)
  → Deploy to Cloudflare Pages (incl. functions/ Pages Function)
  → Cloudflare Access provides OTP email authentication

Browser → /api/data/dora.json
  → Cloudflare Access gate (OTP email) injects a signed JWT
  → Pages Function (functions/api/data/[file].ts) verifies the JWT
  → on success, streams the file from the PRIVATE R2 bucket binding
```

### Why a Pages Function instead of a public bucket?

The R2 bucket is **private** — its `r2.dev` public access is disabled. Data is
served only through the Access-gated Pages Function, which verifies the
Cloudflare Access JWT (`Cf-Access-Jwt-Assertion`) on every request before
touching R2. This means the raw data files are never reachable without passing
the OTP email gate — a frontend-only password would not provide that guarantee.

## Live Site

`https://dora-pipeline.pages.dev` (protected by Cloudflare Access — OTP via email)

## Required GitHub Secrets

Add these in **Settings → Secrets → Actions**:

| Secret | Description |
|--------|-------------|
| `GH_API_READ_TOKEN` | GitHub PAT with `read:org` + `repo` read scopes (secret names can't use the reserved `GITHUB_` prefix) |
| `CLOUDFLARE_API_TOKEN` | CF API token with Pages + R2 write permissions |
| `CLOUDFLARE_ACCOUNT_ID` | Your Cloudflare account ID |
| `R2_BUCKET_NAME` | R2 bucket name, e.g. `dora-pipeline-data` |
| `VITE_R2_BASE_URL` | Path to the Access-gated data API: `/api/data` |
| `OWNER` | GitHub org/user (e.g. `Focus-Bear`) |
| `REPO` | GitHub repo name (e.g. `mobile-app`) |
| `SENTRY_TOKEN` | Sentry API token |
| `SENTRY_ORG` | Sentry org slug |
| `SENTRY_PROJECT` | Sentry project slug |

> ⚠️ `GH_TOKEN` and `GH_REPO_TOKEN` are no longer used. Replace with `GH_API_READ_TOKEN`.

## Cloudflare Setup (One-Time)

### 1. Create R2 Bucket (PRIVATE)

1. Cloudflare Dashboard → **R2** → **Create Bucket** → name: `dora-pipeline-data`
2. **Keep public access DISABLED.** Under the bucket's **Settings → Public access**,
   make sure the `r2.dev` URL is **not** enabled and there is no custom public domain.
   The data must only be reachable through the Pages Function.
3. No CORS policy is needed — the browser fetches data from the same origin
   (`/api/data/*`), not directly from R2.

The bucket is bound to the Pages Function as `DORA_BUCKET` via `wrangler.toml`.

### 2. Create Cloudflare Pages Project

Either:
- Cloudflare Dashboard → **Pages** → **Create Project** → Connect to Git → select `Focus-Bear/dora_pipeline`
- Or let the workflow create it automatically via `wrangler pages deploy`

Project name must be: `dora-pipeline`

### 3. Enable Cloudflare Access (Password Protection)

1. Cloudflare Dashboard → **Zero Trust** → **Access** → **Applications** → **Add Application**
2. Type: **Self-hosted**
3. Name: `DORA Pipeline`
4. Domain: `dora-pipeline.pages.dev`
5. Policy: Add rule → Action: **Allow** → Include: emails ending in `@focusbear.io`
6. Authentication method: **One-time PIN** (OTP via email)
7. Save
8. Open the application's **Overview** and copy the **Application Audience (AUD) tag** —
   you need it for the Pages Function env vars below.

### 4. Configure the Pages Function env vars

The data API Pages Function (`functions/api/data/[file].ts`) verifies the Access
JWT and needs two variables. Set them under
**Pages → dora-pipeline → Settings → Environment variables** (Production):

| Variable | Value |
|----------|-------|
| `CF_ACCESS_TEAM_DOMAIN` | Your Zero Trust team domain, e.g. `https://focusbear.cloudflareaccess.com` (no trailing slash) |
| `CF_ACCESS_AUD` | The Application Audience (AUD) tag from step 3.8 |

If either is missing the function **fails closed** (returns 500) and serves no data.

### 5. Create Cloudflare API Token

1. Cloudflare Dashboard → **Profile** → **API Tokens** → **Create Token**
2. Permissions needed:
   - `Cloudflare Pages: Edit`
   - `R2 Storage: Edit`
3. Copy token → add as `CLOUDFLARE_API_TOKEN` in GitHub secrets

## Local Development

```bash
# Install dependencies
npm ci

# Create local env (leave VITE_R2_BASE_URL empty to use local dora.json)
cp .env.local.example .env.local

# Place a local dora.json in the project root for dev
# Then run dev server
npx vite

# Build for production
npx vite build
```

## Data Upload (Manual)

```bash
export CLOUDFLARE_API_TOKEN=...
export CLOUDFLARE_ACCOUNT_ID=...
export R2_BUCKET_NAME=dora-pipeline-data

# Dry run first
bash scripts/upload-to-r2.sh --dry-run

# Then upload
bash scripts/upload-to-r2.sh
```

## Triggering Manually

Go to **Actions** → **DORA Metrics Pipeline** → **Run workflow**.
