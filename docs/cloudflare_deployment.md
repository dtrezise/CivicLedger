# Cloudflare Deployment

## Delivery Model

CivicLedger uses GitHub as the source, review, CI, scheduled-data, and audit
system. Cloudflare Workers Static Assets is the primary public delivery target
for the generated `pages-site/` workbench. GitHub Pages remains active during
the production stabilization period as an independent fallback. Both hosts
publish the same committed and validated `pages-site/` artifact; deployment
workflows do not regenerate disclosure or public data independently.

Heavy source retrieval, OCR, parsing, validation, and dataset generation remain
in GitHub Actions or the local Docker environment. Cloudflare receives only the
validated static release artifact; it does not become the system of record.

## Deployment Environments

- Development: local Docker services and `python3 -m http.server` for the static workbench.
- Continuous validation: `.github/workflows/ci.yml` on every push and pull request.
- Current public fallback: GitHub Pages from `.github/workflows/pages.yml`.
- Cloudflare production: automatic `.github/workflows/cloudflare-production.yml` deployment after successful `main` CI to `https://civic-ledger.dan-a2c.workers.dev/`.
- Cloudflare usage: daily `.github/workflows/cloudflare-usage.yml` request and asset-footprint evidence.
- Emergency rollback: guarded `.github/workflows/cloudflare-rollback.yml` restoration followed by public smoke checks.
- Rollback rehearsal: monthly and on-demand `.github/workflows/cloudflare-rollback-rehearsal.yml` exercise against a temporary isolated worker that is deleted after verification.

## Production Status

The first Cloudflare deployment completed successfully on 2026-07-13 from commit
`e7f0f80` in GitHub Actions run `29249340674`. The release uploaded 422 static
assets and passed the public-data, provenance, ranking, release-contract, and
Cloudflare asset-limit gates before deployment. The pilot was accepted for
automatic production delivery on 2026-07-13. GitHub Pages remains active as the
public fallback.

## Cloudflare Bootstrap

1. Enable the account `workers.dev` subdomain.
2. Create an API token constrained to the CivicLedger account with
   `Workers Scripts:Edit` for static deployment.
3. Create a separate token with `Account Analytics:Read` for scheduled usage
   reporting. Do not add zone, Pages, KV, R2, or write permissions to it.
4. Add `CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_ANALYTICS_TOKEN`, and
   `CLOUDFLARE_ACCOUNT_ID` as GitHub repository
   secrets.
5. Protect the `cloudflare-production` GitHub environment with a `main`-only
   deployment branch policy.

The API token value belongs only in Cloudflare and GitHub Actions secrets. The
ignored local inventory records metadata and storage locations, never raw
values. Credentials must never appear in committed files, command output,
release artifacts, or workflow summaries.

## Local Validation

```bash
python scripts/check_cloudflare_assets.py
npx wrangler deploy --dry-run --config wrangler.jsonc
```

The compatibility check enforces the Workers Static Assets limits of 20,000
files per version and 25 MiB per file. CivicLedger's stricter release-performance
budgets still apply independently.

## Automatic Deployment

```bash
git push origin main
gh run list --repo dtrezise/CivicLedger --workflow cloudflare-production.yml
```

After `CI` succeeds on `main`, the workflow re-runs the public-data, provenance, ranking, accessibility,
interaction, link, performance, determinism, checksum, and Cloudflare asset
gates before deployment. It writes the source commit and dataset version into
`release.json`, publishes the static artifact, verifies representative HTTP and
JSON endpoints, verifies the custom 404 response, checks security and cache
headers, runs the workbench in a mobile browser, compares release identity with
GitHub Pages, and proves that a prior Cloudflare version remains available. A
failed pre-deployment gate cannot publish a new production version. Any failed
gate also produces a machine-readable rollback recommendation; rollback remains
an explicit guarded action.

Each successful release retains a 90-day GitHub artifact containing the asset
footprint, HTTP and mobile smoke reports, Pages parity report, Cloudflare version
inventory, active deployment status, rollback readiness, preview rehearsal, gate
outcomes, and rollback recommendation.

## Security And Caching

`pages-site/_headers` is the committed source of truth for production response
headers. HTML, the custom 404 response, and release metadata revalidate
immediately. Deterministically content-hashed CSS, application JavaScript, and
the self-hosted ECharts runtime use one-year immutable caches. Public data
partitions use one-hour caches with stale-while-revalidate, and the favicon uses
a one-day cache. Security headers enforce content-source, framing, referrer,
browser-feature, MIME, and transport policies. Every runtime asset includes
subresource integrity.

## Usage Tracking

The daily usage workflow records seven-day account-level Worker request, error,
and subrequest metrics plus the current static corpus size and growth from the
committed baseline. Reports are retained as 90-day GitHub artifacts.

Exact visitor transfer bytes are a zone-analytics metric. The current
`workers.dev`-only release has no customer zone, so the report records bandwidth
as `awaiting_custom_zone` rather than inventing an estimate. When a custom domain
is added, supply its zone scope and extend the tracker with
`httpRequestsAdaptiveGroups.sum.edgeResponseBytes`. Workers Static Assets
requests themselves remain free and unlimited.

## R2 Growth Path

Workers Static Assets should continue serving the interactive shell and compact
query partitions. The prepared object layout, release pointer, retention,
credentials, CORS, and activation gates are documented in
`docs/r2_public_data_architecture.md`. No R2 resource is active. The browser must
never receive private evidence-bucket credentials.

## Rollback

GitHub Pages remains independently deployable. Cloudflare Workers retains up to
the recent deployment versions supported by Wrangler rollback. Every production
release proves that a prior version exists. The emergency rollback workflow
requires an explicit version ID and confirmation, restores that version, then
re-runs HTTP, dataset, security, cache, and rollback-readiness checks. A
Cloudflare failure must not mutate generated data or interrupt GitHub Pages.

The isolated rehearsal creates a uniquely named worker, deploys two minimal
versions, restores the first version with Wrangler rollback, verifies the
restored response at the edge, retains 90-day evidence, and deletes the worker.
It never deploys CivicLedger data or mutates the production worker.
