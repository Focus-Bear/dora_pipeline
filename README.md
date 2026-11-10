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
| `GH_API_READ_TOKEN` | GitHub PAT with `read:org` + `repo` + `read:project` (fine-grained: Contents, Issues, Pull requests, Actions read + org Projects read). Secret names can't use the reserved `GITHUB_` prefix |
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

## Dev report and repo summary metrics (`cliq_notify.py`, `repo_summary.py`)

The daily Zoho Cliq #scrum post is the dev report. It covers the **last 7 days**,
and every figure is shown next to the **7 days before** ("prev"). The same
figures, for 7 or 30 days, are written to `repo_summary_7d.csv` /
`repo_summary_30d.csv` for the dashboard's "Overall Velocity Report" page.
Per repo, plus totals:

| Section | Figure | Source |
|---------|--------|--------|
| 1. Dev velocity | PRs merged | GitHub search `is:pr is:merged merged:<window>`, per repo |
| | PRs open now (draft / approved split) | GitHub search `is:pr is:open`, per repo |
| 2. Quality | New issues (and how many are labelled `bug`) | GitHub search `is:issue created:<window>`, per repo |
| | QA failed of QA tested | The repo's board: issues whose Status moved into its QA Failed column (failed) or its QA Failed / passed column (tested) in the window |
| 3. QA backlog | Issues in Ready for QA now, and 7 days ago | The repo's board: current Status; the 7-days-ago count is rebuilt from the status-change history |
| | How long each has waited, median, oldest | Time since the board item's Status value was last set |
| Appendix | Days since last release | Per platform, see below |

All search counts for a repo come from one batched GraphQL query; board data
comes from Projects v2 (`ProjectV2ItemStatusChangedEvent` timeline events).

**What counts as a QA result.** There is no `qa-failed` label in any Focus Bear
repo, so QA results come from board Status only. A move counts only when it
comes out of the board's QA stage: its Ready for QA column or a column QA works
in, such as QA in Progress or For Dev QA (a failure may also come out of the
passed column). Each repo lists these columns in `REPOS`
(`qa.ready` / `qa.testing` / `qa.passed` / `qa.failed`). This leaves out issues
filed straight into QA Failed and bulk board clean-ups, which GitHub records
with no status history. Linux has no QA Failed column, and the browser
extension board has no QA columns, so their failure figures show as `–`.

The backlog is per board, so an issue from another repo filed on a repo's board
is counted on that board. Closed issues still in Ready for QA are counted: the
merge closes the issue before QA has checked it.

### Reproducing the report

One command, read-only (GitHub queries only; nothing is posted without
`CLIQ_WEBHOOK_TOKEN`):

```bash
pip install -r requirements.txt
GH_API_READ_TOKEN=$(gh auth token) python cliq_notify.py --dry-run --backlog-csv qa_backlog.csv
```

It prints the Cliq message and writes `qa_backlog.csv`: every issue waiting in
Ready for QA on every board, oldest first, with its link. `--days N` reports a
different window, compared with the N days before it. It takes about 3 minutes.

Release signal per repo (`release_velocity.py`; falls back to GitHub Releases, then tags):

| Repo | Signal |
|------|--------|
| Mac | Newest item in the Sparkle appcast (`downloads.focusbear.io/update/mac/new/latest-version.xml`). GitHub Releases there are per-build QA builds, not user releases |
| Windows | `Last-Modified` of `downloads.focusbear.io/update/windows/update.ini`, the file the app polls |
| Mobile | App Store lookup API `currentVersionReleaseDate` (iOS; Google Play has no public API) |
| Web Dashboard | Last successful `s3-deployment-prod.yaml` run on `main` |
| Backend | Last successful `github-aws-prod-deployment.yaml` / `github-aws-hotfix-deploy.yaml` run |
| Linux | Last successful `build-deb.yml` run on `main` |

To write the dashboard CSVs locally (leave `CLIQ_WEBHOOK_TOKEN` unset so
nothing is posted), and to run the tests:

```bash
GH_API_READ_TOKEN=$(gh auth token) python repo_summary.py
python -m unittest discover -s tests -t .
```

## Triggering Manually

Go to **Actions** → **DORA Metrics Pipeline** → **Run workflow**.
