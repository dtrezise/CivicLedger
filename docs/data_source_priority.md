# Data Source Priority

CivicLedger's core focus is public officials' stock-market trades, related filing/reporting lag, market movement, and neutral context around trade dates and report dates.

## Active

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

The public Pages demo currently uses fixture market-index overlays for SPY, QQQ, DIA, and sector ETFs. These should be replaced with a production market-data provider before any public analytical claims are made from market movement.
