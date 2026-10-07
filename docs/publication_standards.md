# Publication Standards

## Purpose

CivicLedger helps people inspect public financial disclosures alongside sourced government and market context. It is a research and verification tool, not an accusation engine. The system must make it easier to reach the underlying evidence and harder to mistake automation, timing, or missing data for proof.

## Evidence Ladder

| Level | State | Minimum evidence | Public use |
|---|---|---|---|
| L0 | Discovered | Source or filing reference identified | Coverage accounting only |
| L1 | Acquired | Source archived with URL, retrieval time, and hash | Source index and review queue |
| L2 | Extracted | Candidate fields with parser version and evidence spans | Clearly labeled research preview |
| L3 | Reviewed | Attributable reviewer compared every material field with the source | Reviewed record, still subject to editorial context |
| L4 | Publication ready | Review, correction, source, identity, amendment, and release checks pass | Public editorial use |

No automated process may label a record L3 or L4.

## Source Rules

- Prefer official records for filings, votes, orders, rules, court decisions, and agency actions.
- Preserve the original URL, retrieved timestamp, content hash, parser version, and acquisition status.
- Attribute independent reporting to the publisher and separate it from official-source facts.
- Preserve amended and superseded filings; do not silently replace history.
- Treat inaccessible, unindexed, image-only, or unparsed material as declared missingness.

## Claim Rules

- A transaction row establishes only what the reviewed source establishes.
- A value range is a range; midpoint values are visualization aids, not exact transaction amounts.
- Event proximity is a research lead, not proof of causation, intent, knowledge, benefit, or misconduct.
- No row is never proof of no trade. It can also reflect filing scope, acquisition, matching, OCR, parser, or review gaps.
- Market returns describe public price movement; they do not establish portfolio performance or motive.
- Consequential narrative claims require L4 evidence, chronology review, alternative explanations, and right of reply.

## Corrections and Fairness

- Material corrections are append-only, dated, attributable, and linked to the changed record.
- The prior public state remains reproducible through versioned datasets and hashes.
- People and institutions named in consequential reporting receive a reasonable opportunity to respond before publication.
- Responses, denials, documentary conflicts, and unresolved uncertainty are represented fairly.

## Public Product Boundary

Until a human-reviewed corpus and correction channel are operational, the public explorer is a **Research Preview**. Preview rows may support verification work and product evaluation; they may not support accusations, rankings of suspected wrongdoing, or automated investigative conclusions.
