# Validation and Gold Corpus

## Why This Exists

Software regression tests show that code behaves consistently. They do not show that extraction or event ranking is accurate in real public records. CivicLedger therefore maintains separate empirical validation work.

## Disclosure Gold Corpus

- Draw a deterministic, stratified sample across House, Senate, executive, and judicial sources.
- Include machine-readable, scanned, amended, no-transaction, long-table, and ambiguous examples.
- Two reviewers independently label material fields for a calibration subset.
- Resolve disagreements without deleting the original labels.
- Report field precision, recall, exact-match rate, document failure rate, and confidence intervals by source lane.
- Never count an unlabeled document as correct.

## Event-Relevance Review

- Sample candidate and non-candidate relationships across tiers, branches, dates, and event types.
- Review source connection, official involvement, temporal distance, asset/sector scope, and whether the candidate is useful context.
- Measure ranking precision at display cutoffs and reviewer agreement.
- Do not label causation, motive, knowledge, or misconduct.

## Release Thresholds

Thresholds must be set only after the first representative labeled sample. Until then, the synthetic event benchmark remains a deterministic regression fixture and all parser output remains preview-only. Empirical reports must publish sample construction, exclusions, label policy, counts, and uncertainty.
