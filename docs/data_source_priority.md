# Data Source Priority

CivicLedger's core focus is public officials' stock-market trades, related filing/reporting lag, market movement, and neutral context around trade dates and report dates.

## Active

### Tiingo

Status: active

Tiingo is the preferred production market-price provider for ETF and ticker overlays. CivicLedger uses Tiingo end-of-day adjusted close values for neutral post-trade market movement context around trade dates and report dates.

If Tiingo is temporarily rate-limited, the refresh pipeline can fall back to Nasdaq public historical daily close data and labels those series as Nasdaq sourced. Fallback rows use close instead of adjusted close and remain acceptable only as first-draft context until Tiingo can refresh them.

Initial issuer and benchmark overlay symbols:

- AAPL
- MSFT
- GOOGL
- AMZN
- NVDA
- META
- TSLA
- JPM
- V
- JNJ
- SPY
- QQQ
- IWM
- BND
- VFIAX
- DIA
- XLK
- XLF
- XLE
- XLV
- XLI

### FRED

Status: active

FRED is the first non-trade contextual integration because macroeconomic series can directly contextualize broad stock-market conditions around disclosed trades:

- Federal funds rate overlays.
- CPI and inflation backdrop.
- CPI release-date event overlays.
- Treasury yield overlays.
- Recession-regime overlays.
- Labor-market context.

FRED overlays must always be labeled as context only. They do not imply causation, intent, legality, ethics, or investment performance.

## Watchlist

### Treasury Fiscal Data

Status: watchlist

Potentially useful for fiscal and rate context, but FRED covers the first-pass macro layer. Revisit after trade timelines and issuer-level market matching are stronger.

### BLS

Status: watchlist

BLS can validate or deepen labor and inflation releases later. For the first draft, FRED is sufficient for macro context.

## Deferred

### FEC

Status: deferred

FEC data is politically important but less directly tied to public officials' stock trades. It should stay out of the core experience until there is a clear trade-context question that campaign-finance data answers without muddying the product.

### USAspending

Status: deferred

USAspending could become highly relevant after CivicLedger can map ticker symbols to operating companies, subsidiaries, award recipients, agencies, and contract/grant events. Until that entity-resolution layer exists, USAspending is likely to create noisy or misleading context.

## Market Price Data

The public Pages demo now prefers Tiingo adjusted close values for individual stock tickers, broad-market ETFs, sector ETFs, bond ETFs, and one mutual-fund benchmark, with a labeled Nasdaq close fallback when Tiingo is temporarily rate-limited. Each mapped ticker carries an issuer name, asset class, sector, and preferred benchmark symbol so trade rows can show:

- Exact trade-date to report-date market movement.
- 7, 30, and 90 calendar-day movement windows.
- A compact price path around the trade date.
- The relevant benchmark movement beside the traded asset.
- A coverage report and anomaly count from the refresh workflow.

Market-price overlays remain context only and must not imply causation, intent, legality, ethics, or investment performance. Official disclosure ingestion remains the next priority after the ticker-overlay layer is stable.
