# Cloudflare Deployment

## Delivery Model

CivicLedger uses GitHub as the source, review, CI, scheduled-data, and audit
system. Cloudflare Workers Static Assets is the parallel public delivery target
for the generated `pages-site/` workbench. GitHub Pages remains active during
the pilot and rollback period.

Heavy source retrieval, OCR, parsing, validation, and dataset generation remain
in GitHub Actions or the local Docker environment. Cloudflare receives only the
validated static release artifact; it does not become the system of record.

## Deployment Environments

- Development: local Docker services and `python3 -m http.server` for the static workbench.
- Continuous validation: `.github/workflows/ci.yml` on every push and pull request.
- Current public fallback: GitHub Pages from `.github/workflows/pages.yml`.
- Cloudflare pilot: manual `.github/workflows/cloudflare-pilot.yml` deployment to `civic-ledger.<account-subdomain>.workers.dev`.
- Production cutover: enable only after a sustained parity period and public smoke checks.

## Cloudflare Bootstrap

1. Enable the account `workers.dev` subdomain.
2. Create an API token from Cloudflare's `Edit Cloudflare Workers` template,
   constrained to the CivicLedger account. Do not add zone or R2 permissions to
   the static-deployment token.
3. Add `CLOUDFLARE_API_TOKEN` and `CLOUDFLARE_ACCOUNT_ID` as GitHub repository
   secrets.
4. Run the `Deploy Cloudflare Pilot` workflow manually.
5. Verify the emitted deployment URL before changing any production routing.

The API token value belongs only in Cloudflare, GitHub Actions secrets, and the
ignored local secret inventory. It must never appear in committed files, command
output, release artifacts, or workflow summaries.

## Local Validation

```bash
python scripts/check_cloudflare_assets.py
npx wrangler deploy --dry-run --config wrangler.jsonc
```

The compatibility check enforces the Workers Static Assets limits of 20,000
files per version and 25 MiB per file. CivicLedger's stricter release-performance
budgets still apply independently.

## Deployment

```bash
gh workflow run cloudflare-pilot.yml --repo dtrezise/CivicLedger
gh run watch --repo dtrezise/CivicLedger
```

The workflow re-runs the public-data, provenance, ranking, accessibility,
interaction, link, performance, determinism, checksum, and Cloudflare asset
gates before deployment. A failed gate cannot publish a new pilot version.

## R2 Growth Path

Workers Static Assets should continue serving the interactive shell and compact
query partitions. If the public evidence corpus outgrows repository or deploy
budgets, create separate R2 buckets for public release data and restricted raw
evidence. R2 activation, bucket creation, lifecycle rules, CORS, custom domains,
and a separate least-privilege upload token are deliberately outside the static
pilot. The browser must never receive private evidence-bucket credentials.

## Rollback

GitHub Pages remains independently deployable throughout the pilot. Cloudflare
Workers also retains deployment versions for rollback. A Cloudflare failure must
not mutate generated data or interrupt the GitHub Pages release.
