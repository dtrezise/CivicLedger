# Current Events Update Policy

## Daily Scope

The scheduled updater refreshes official rosters, House and Senate disclosure indexes, current House PTRs, presidential OGE indexes, official federal events, market series, source snapshots, extraction artifacts, and the public static dataset. Deep Congress involvement and Senate report-page acquisition run weekly or by manual dispatch.

## Source Priority

1. Official filing and disclosure portals.
2. Congress.gov, GovInfo, Federal Register, agency, court, and SEC records.
3. Attributed publisher reporting used only as clearly labeled context.
4. Market and macro providers used descriptively, never as proof of impact or motive.

## Failure Behavior

- A failed refresh does not overwrite the last validated public dataset.
- The public site receives a visible failure status and must not describe the retained snapshot as current.
- Provider-specific snapshots may be retained only when their integrity checks pass and the fallback is declared.
- Generated data is committed only after application, evidence, static-site, and release-gate tests pass.
- Failure telemetry is retained as a private workflow artifact; public status contains no secrets or diagnostic payloads.

## Current-Event Integrity

An event enters the public catalog only with date, label, type, source URL, source tier, and provenance. Candidate relationships are ranked separately from official involvement. New events do not become evidence about a trade merely because they occur nearby in time.
