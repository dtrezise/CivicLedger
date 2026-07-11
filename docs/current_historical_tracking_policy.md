# Current and Historical Tracking Policy

CivicLedger treats prior public service as a static historical record and current public service as a monitored source record.

## Scope

- Congressional foundation scope starts with the 111th through 119th Congresses.
- Presidential-term scope begins with the Obama administration and currently
  includes Obama 44, Trump 45, Biden 46, and Trump 47.
- Congressional service is indexed by Bioguide ID, Congress number, chamber, state, district, and party.
- Executive and judicial service remain indexed through official source-specific identifiers until a stronger cross-source identifier is available.

## Static Historical Records

Officials no longer holding a role should not require live tracking after their source-backed service record is captured, normalized, reviewed, and committed to the static dataset.

Historical refreshes should be intentional and versioned when:

- an official source corrects a record,
- a better official source becomes available,
- the parser model changes materially,
- or a reviewer promotes a higher-confidence record.

## Current Records

Current officials should be monitored through official sources where available:

- Congress.gov member records for House and Senate congressional service history.
- House Clerk current member XML for current House roster cross-checks.
- Senate.gov current senators XML for current Senate roster cross-checks.
- OGE, House, Senate, and judiciary disclosure sources for financial filings.

Current records should keep provenance metadata that identifies retrieval date, source URL, source tier, parser version, and any source-specific identifier such as Bioguide ID.

## Promotion Rule

New or refreshed records should enter the system as raw or preview records first. They become public-facing static records only after parser output passes regression checks and review confirms the official-source provenance is adequate.

## Refresh Rule

Past Congresses and completed administrations should be refreshed only by explicit data-maintenance tasks. The current Congress and current administration are eligible for scheduled refreshes. Historical disclosure backfills remain versioned, resumable maintenance jobs rather than daily live-tracking work.
