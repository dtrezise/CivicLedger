# Future R2 Public Data Architecture

## Status

This design is prepared but not activated. CivicLedger continues to publish the
validated `pages-site/` artifact through Workers Static Assets. No R2 bucket,
binding, public hostname, upload credential, or billable storage resource is
created by the current configuration.

## Purpose

R2 becomes useful when historical disclosure documents and versioned public
partitions are too large for a practical Git checkout or a compact static-asset
release. GitHub remains the source, review, CI, issue, and release-audit system.
R2 would become a delivery store for immutable public data, not the authoritative
place where source records are edited.

## Storage Boundaries

Use separate buckets with separate credentials and routes:

- `civicledger-public-data`: reviewed public manifests, query partitions, and public evidence derivatives.
- `civicledger-restricted-evidence`: raw or review-pending documents that must never have a public route or browser credential.

The static application shell, CSS, JavaScript, icons, compact indexes, and
release metadata remain in Workers Static Assets. Secrets, review notes, local
archives, and provider credentials never enter either public artifacts or
client-side code.

## Object Layout

Public objects are immutable and content-addressed beneath a release prefix:

```text
releases/{dataset_version}/manifest.json
releases/{dataset_version}/branches/{branch}/{source}/{year}/{sha256}.json.gz
releases/{dataset_version}/market/{symbol}/{year}/{sha256}.json.gz
releases/{dataset_version}/evidence/{source}/{year}/{document_id}/{sha256}.pdf
pointers/current.json
```

`pointers/current.json` contains only a validated release identifier, manifest
URL, checksum, publication time, and rollback predecessor. The browser first
loads that small pointer, then verifies the selected release manifest before
requesting partitions.

## Release Procedure

1. Build the complete public corpus in GitHub Actions from a pinned commit.
2. Run schema, provenance, ranking, accessibility, determinism, and checksum gates.
3. Upload immutable objects to a staging release prefix using a dedicated R2 write token.
4. Re-download representative objects and verify bytes, hashes, content types, and cache headers.
5. Publish the immutable release manifest.
6. Atomically replace `pointers/current.json` only after every verification passes.
7. Run the same public HTTP and dataset smoke checks used by the static deployment.
8. Retain the prior pointer so rollback changes one small object rather than re-uploading the corpus.

No workflow may overwrite an object under an existing release prefix. A
correction creates a new dataset version with provenance that identifies the
superseded release.

## Delivery Policy

- Public immutable objects: `Cache-Control: public, max-age=31536000, immutable`.
- Current pointer: `Cache-Control: public, max-age=60, must-revalidate`.
- Release manifests: `Cache-Control: public, max-age=300, must-revalidate`.
- CORS allowlist: the Cloudflare production hostname, the GitHub Pages fallback, and approved preview origins only.
- Public downloads use a dedicated data hostname once a custom domain strategy is approved.
- The restricted bucket has no public development URL, custom domain, or permissive CORS policy.

## Credentials

Use three non-overlapping Cloudflare tokens:

- Static deployment: Workers Scripts Write for the CivicLedger account.
- Analytics: Account Analytics Read only.
- Future R2 publisher: Object Read and Write only for the public-data bucket.

The browser receives no Cloudflare credential. GitHub environment protection and
branch policy guard production publishing. The future restricted-evidence token
must be separate from the public publisher and unavailable to public release jobs.

## Retention And Recovery

Keep all published manifests and at least the current and two prior complete
release generations online. Older public releases can move to a lower-cost
retention class only after their manifests and source provenance remain
resolvable. Restricted raw evidence follows the project's legal and provenance
retention policy rather than the public cache policy.

Rollback replaces the current pointer with a previously verified pointer, runs
HTTP smoke checks, and records the target release, operator, reason, and GitHub
run. Bucket deletion and lifecycle changes are never part of rollback.

## Activation Gates

Activate R2 only when one or more of these conditions becomes sustained:

- The public deploy approaches 15,000 static files or an individual file approaches 20 MiB.
- The public release corpus exceeds 500 MiB and materially slows routine deployment.
- Large evidence documents cause repository clones or GitHub Actions artifacts to become operationally expensive.
- A stable custom domain and cross-project hosting strategy is ready.

Before activation, run a cost estimate, create lifecycle and CORS tests, add an
R2 emulator integration test, rehearse pointer rollback, and document a public
data availability objective.
