# API Sources and Local Keys

CivicLedger can use local API keys through ignored `.env` values. Real keys must never be committed.

## Configured Local Variables

- `CONGRESS_GOV_API_KEY`: Congress.gov member, bill, and legislative data.
- `FRED_API_KEY`: Federal Reserve Economic Data macroeconomic series.
- `TIINGO_API_KEY`: Tiingo end-of-day stock, ETF, and crypto price data.
- `FEC_API_KEY`: Federal Election Commission campaign finance data.
- `DATA_GOV_API_KEY`: api.data.gov-backed federal APIs where required.
- `CENSUS_API_KEY`: Census API demographic and geography datasets.
- `BLS_API_KEY`: Bureau of Labor Statistics datasets.
- `SEC_EDGAR_USER_AGENT`: SEC-compliant application and contact identity; this is not a secret.

## Current Product Priority

- FRED is active for macro context around stock-market trades.
- Tiingo is active for production ETF, ticker, and crypto market-price overlays.
- BLS and Treasury Fiscal Data are watchlist sources.
- FEC is deferred because campaign-finance data is not directly tied to stock-trade context.
- USAspending is deferred until ticker/company/entity matching can connect public companies to federal awards or contract events.
- SEC EDGAR is active for review-gated issuer filing context around ticker-linked disclosures.
- GDELT DOC 2.0 is configured as a keyless, pluggable historical-news discovery provider. Provider outages remain explicit coverage gaps.
- Senate eFD acquisition is active under an explicit portal-terms acknowledgement and one-second request pacing.

## Keyless or Documentation-Only Sources

- `USASPENDING_API_DOCS_URL`: USAspending API documentation.
- `TREASURY_FISCALDATA_API_DOCS_URL`: Treasury Fiscal Data API documentation.

## Handling Rules

- Store real values only in ignored `.env` or external secret stores.
- Keep the local token inventory in ignored `.secrets/api_tokens.local.md`.
- Commit only variable names, source metadata, and non-secret documentation URLs.
- Use GitHub repository secrets for scheduled refresh workflows.
- Do not print API keys in logs, test output, build output, or generated public data.

## Scheduled Refresh

The `.github/workflows/data-refresh.yml` workflow refreshes the Congress.gov roster, public official roles, disclosure indexes, OGE documents, FRED context, Tiingo prices, SEC filing context, asset resolution, market reactions, and Pages partitions daily. Heavier Senate report-page acquisition and official-event involvement refresh weekly or on a manual run.

Required repository secrets:

- `CONGRESS_GOV_API_KEY`
- `FRED_API_KEY`
- `TIINGO_API_KEY`

Manual run:

```bash
gh workflow run data-refresh.yml --repo dtrezise/CivicLedger
```
