# Plan: Migrate dora_pipeline to Cloudflare Pages + R2 (Issue #12)

## Problem Statement

The current setup has two key pain points:

1. **Git history pollution**: Daily cron commits `dora.json`, `dora.sqlite`, and CSV files directly to the repo, creating noise in the history and bloating the repository over time.
2. **No authentication**: The GitHub Pages site is publicly accessible with no password protection.

## Current Architecture

```
GitHub Actions cron (daily)
  → Python scripts generate: dora.json, dora.sqlite, repo_summary*.csv
  → Committed to repo (via GH_REPO_TOKEN)
  → Vite build bundles dora.json (static import)
  → CSVs copied to dist/public/
  → Deployed to GitHub Pages (via GH_REPO_TOKEN)
```

**Key data loading mechanisms discovered:**
- `client/src/lib/dora-calculations.ts`: Uses `import doraData from "./../../../dora.json"` — **static import, bundled at build time**
- `client/src/pages/repo-summary.tsx`: Uses `fetch(${baseUrl}repo_summary_${days}d.csv)` — **runtime fetch from BASE_URL**
- `vite.config.ts`: `base: '/dora_pipeline/'` — hardcoded for GitHub Pages subdirectory

## Target Architecture

```
GitHub Actions cron (daily)
  → Python scripts generate: dora.json, dora.sqlite, repo_summary*.csv
  → Upload data files to Cloudflare R2 (public bucket)
  → Vite build (fetches dora.json from R2 at runtime, no bundling)
  → Deploy to Cloudflare Pages via Wrangler
  → Cloudflare Access provides password protection (One-Time Pin)
```

## Required Changes

### 1. `client/src/lib/dora-calculations.ts`

**Change static import to runtime fetch.**

Current:
```typescript
import doraData from "./../../../dora.json";

export function loadDoraData(): DoraData {
  return doraData as DoraData;
}
```

Replace with async fetch:
```typescript
const R2_BASE_URL = import.meta.env.VITE_R2_BASE_URL || '';

export async function loadDoraData(): Promise<DoraData> {
  const url = R2_BASE_URL ? `${R2_BASE_URL}/dora.json` : '/dora.json';
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`Failed to fetch DORA data: ${response.statusText}`);
  }
  return response.json() as Promise<DoraData>;
}
```

### 2. `client/src/pages/dashboard.tsx`

Update `useEffect` to handle the now-async `loadDoraData()`:

```typescript
useEffect(() => {
  loadDoraData()
    .then(doraData => setData(doraData))
    .catch(error => console.error("Error loading DORA data:", error))
    .finally(() => setLoading(false));
}, []);
```

### 3. `client/src/pages/repo-summary.tsx`

Update the CSV fetch URL to use R2:

```typescript
const R2_BASE_URL = import.meta.env.VITE_R2_BASE_URL || '';

// In fetchData():
const csvFile = R2_BASE_URL
  ? `${R2_BASE_URL}/repo_summary_${days}d.csv`
  : `${baseUrl}repo_summary_${days}d.csv`;
```

### 4. `vite.config.ts`

Change `base` from hardcoded `/dora_pipeline/` to root (Cloudflare Pages serves from root):

```typescript
base: '/',
```

Remove the Replit-specific plugins (optional cleanup):
- `@replit/vite-plugin-runtime-error-modal`
- `@replit/vite-plugin-cartographer`

### 5. `.github/workflows/dora-metrics.yml`

**Complete rewrite.** New workflow:

```yaml
name: DORA Metrics Pipeline

on:
  schedule:
    - cron: "0 12 * * *"   # daily at 12:00 UTC
  workflow_dispatch:

jobs:
  collect-and-deploy:
    runs-on: ubuntu-latest
    environment:
      name: production
    steps:
      - name: Checkout repo
        uses: actions/checkout@v4
        # No token needed — we are NOT pushing back to the repo

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.10"

      - name: Install Python dependencies
        run: |
          python -m pip install --upgrade pip
          pip install -r requirements.txt

      - name: Run DORA pipeline
        env:
          GITHUB_API_READ_TOKEN: ${{ secrets.GITHUB_API_READ_TOKEN }}
          OWNER: ${{ secrets.OWNER }}
          REPO: ${{ secrets.REPO }}
          SENTRY_TOKEN: ${{ secrets.SENTRY_TOKEN }}
          SENTRY_ORG: ${{ secrets.SENTRY_ORG }}
          SENTRY_PROJECT: ${{ secrets.SENTRY_PROJECT }}
        run: python dora_pipeline.py

      - name: Run Repo Summary script
        env:
          GITHUB_API_READ_TOKEN: ${{ secrets.GITHUB_API_READ_TOKEN }}
        run: python repo_summary.py

      - name: Install Wrangler
        run: npm install -g wrangler

      - name: Upload data files to R2
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CLOUDFLARE_API_TOKEN }}
          CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CLOUDFLARE_ACCOUNT_ID }}
        run: |
          wrangler r2 object put ${{ secrets.R2_BUCKET_NAME }}/dora.json --file=dora.json
          wrangler r2 object put ${{ secrets.R2_BUCKET_NAME }}/dora.sqlite --file=dora.sqlite
          wrangler r2 object put ${{ secrets.R2_BUCKET_NAME }}/repo_summary.csv --file=repo_summary.csv
          wrangler r2 object put ${{ secrets.R2_BUCKET_NAME }}/repo_summary_7d.csv --file=repo_summary_7d.csv
          wrangler r2 object put ${{ secrets.R2_BUCKET_NAME }}/repo_summary_30d.csv --file=repo_summary_30d.csv

      - name: Setup Node.js
        uses: actions/setup-node@v4
        with:
          node-version: '20'
          cache: 'npm'

      - name: Install Node dependencies
        run: npm ci

      - name: Build Vite project
        env:
          VITE_R2_BASE_URL: ${{ secrets.VITE_R2_BASE_URL }}
          NODE_ENV: production
        run: npx vite build

      - name: Deploy to Cloudflare Pages
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CLOUDFLARE_API_TOKEN }}
          CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CLOUDFLARE_ACCOUNT_ID }}
        run: |
          npx wrangler pages deploy dist/public \
            --project-name=dora-pipeline \
            --branch=main
```

### 6. `dora_pipeline.py` — Token rename

Find all references to `GH_TOKEN` and replace with `GITHUB_API_READ_TOKEN`:

```python
# Before:
gh_token = os.environ.get("GH_TOKEN")

# After:
gh_token = os.environ.get("GITHUB_API_READ_TOKEN")
```

### 7. `repo_summary.py` — Token rename

Same change:
```python
# Before:
gh_token = os.environ.get("GH_TOKEN")

# After:
gh_token = os.environ.get("GITHUB_API_READ_TOKEN")
```

### 8. `.gitignore`

Add data files to gitignore (they should no longer be tracked):

```gitignore
# Data files — now stored in R2, not committed
dora.json
dora.sqlite
repo_summary.csv
repo_summary_7d.csv
repo_summary_30d.csv
```

> ⚠️ **Note**: These files currently exist in git history. After updating `.gitignore`, run `git rm --cached dora.json dora.sqlite repo_summary*.csv` to stop tracking them. They will remain in git history but won't be committed going forward.

## GitHub Secrets Changes

### Remove
- `GH_TOKEN` — replaced by `GITHUB_API_READ_TOKEN`
- `GH_REPO_TOKEN` — no longer needed (no git push of data)

### Add
| Secret | Value |
|--------|-------|
| `GITHUB_API_READ_TOKEN` | GitHub PAT with `read:org` and `repo` read scopes |
| `CLOUDFLARE_API_TOKEN` | CF API token with Pages + R2 write permissions |
| `CLOUDFLARE_ACCOUNT_ID` | Your Cloudflare account ID |
| `R2_BUCKET_NAME` | e.g. `dora-pipeline-data` |
| `VITE_R2_BASE_URL` | Public R2 bucket URL, e.g. `https://pub-xxx.r2.dev` |

### Keep (unchanged)
- `OWNER`
- `REPO`
- `SENTRY_TOKEN`
- `SENTRY_ORG`
- `SENTRY_PROJECT`

## Cloudflare Setup Instructions (Manual Steps)

These steps are done once in the Cloudflare dashboard:

### 1. Create R2 Bucket
1. Cloudflare Dashboard → R2 → Create Bucket → name: `dora-pipeline-data`
2. Enable **Public Access** on the bucket
3. Note the public URL: `https://pub-<hash>.r2.dev` → use as `VITE_R2_BASE_URL`
4. Set CORS policy on the bucket:
   ```json
   [
     {
       "AllowedOrigins": ["https://dora-pipeline.pages.dev", "https://*.dora-pipeline.pages.dev"],
       "AllowedMethods": ["GET"],
       "AllowedHeaders": ["*"]
     }
   ]
   ```

### 2. Create Cloudflare Pages Project
1. Cloudflare Dashboard → Pages → Create Project → **Connect to Git** → select `Focus-Bear/dora_pipeline`
2. Or skip git connection — the workflow uses `wrangler pages deploy` directly
3. Project name: `dora-pipeline`
4. The site will be at `https://dora-pipeline.pages.dev`

### 3. Create Cloudflare Access Application (Password Protection)
1. Cloudflare Dashboard → Zero Trust → Access → Applications → Add Application
2. Application type: **Self-hosted**
3. Application name: `DORA Pipeline`
4. Application domain: `dora-pipeline.pages.dev`
5. Policy name: `OTP Access`
6. Add a policy rule:
   - Action: **Allow**
   - Include: `Emails ending in @focusbear.io` (or specific emails)
   - OR use **One-time PIN** for anyone with an approved email
7. Save the application

> **Alternative**: Use a Cloudflare Access "Service Auth" token approach for even simpler password-style protection — but OTP via email is the recommended approach for a small team.

### 4. Create Cloudflare API Token (for GitHub Actions)
1. Cloudflare Dashboard → Profile → API Tokens → Create Token
2. Use template: **Edit Cloudflare Workers** (or create custom)
3. Permissions needed:
   - `Cloudflare Pages: Edit`
   - `R2 Storage: Edit`
4. Copy the token → add as `CLOUDFLARE_API_TOKEN` in GitHub secrets

## Implementation Steps for Codebeard

1. **`dora_pipeline.py`**: Replace `os.environ.get("GH_TOKEN")` with `os.environ.get("GITHUB_API_READ_TOKEN")`
2. **`repo_summary.py`**: Same token rename
3. **`client/src/lib/dora-calculations.ts`**: Replace static `import doraData` with async `fetch()` using `VITE_R2_BASE_URL`
4. **`client/src/pages/dashboard.tsx`**: Update `useEffect` to await the now-async `loadDoraData()`
5. **`client/src/pages/repo-summary.tsx`**: Update CSV fetch to use `VITE_R2_BASE_URL` prefix
6. **`vite.config.ts`**: Change `base: '/dora_pipeline/'` to `base: '/'`
7. **`.github/workflows/dora-metrics.yml`**: Full replacement per the new workflow above
8. **`.gitignore`**: Add data files; run `git rm --cached` for existing tracked files

## Test Approach

- **Local dev**: Create a `.env.local` with `VITE_R2_BASE_URL=` (empty) and keep a local `dora.json` for dev testing — the fallback path in `loadDoraData()` will serve it from the dev server
- **Staging**: After merging, trigger `workflow_dispatch` manually and verify:
  - R2 bucket receives the files
  - CF Pages build succeeds
  - Site loads at `dora-pipeline.pages.dev`
  - Cloudflare Access OTP gate prompts for email
- **Data integrity**: Compare DORA metrics on new site against last known GitHub Pages deployment

## Edge Cases & Risks

- **CORS on R2**: Must configure CORS correctly on the R2 bucket before the frontend can fetch. If misconfigured, all data will fail to load silently.
- **First deploy**: On first run, R2 files won't exist yet. The `dora_pipeline.py` must succeed before the build step. The workflow already serialises these correctly (R2 upload before build).
- **dora.json in build**: After removing the static import, the file will no longer be bundled. The `dist/public` folder will be smaller but `dora.json` must be in R2 before the site goes live.
- **Existing tracked files**: `dora.json`, `dora.sqlite`, and CSVs are currently tracked in git. After `.gitignore` update, run `git rm --cached` to untrack them. This causes a one-time commit but doesn't delete the files locally or from R2.
- **Cloudflare Pages free tier**: 500 builds/month limit. Daily builds = 30/month — well within limits.
- **Wrangler auth**: The `CLOUDFLARE_ACCOUNT_ID` env var is required alongside `CLOUDFLARE_API_TOKEN` for `wrangler r2` commands to work.

---

🧘 *The river does not force its way through rock — it finds the path of least resistance and shapes the landscape over time. So too shall we redirect data from git history to R2.*
