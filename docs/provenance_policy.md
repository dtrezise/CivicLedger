# Provenance Policy

## Core Principle

Every public-facing record should be traceable to source metadata. Missing source metadata is a data-quality state, not evidence of wrongdoing.

## Required Record Fields

Each filing and normalized trade should expose:

- Original source URL.
- Retrieval timestamp.
- Retrieval source.
- File hash.
- Parser version.
- Dataset version.
- Methodology version.
- Record ID.
- Provenance completeness flag.

## Fixture Data

Fixture records must carry `retrieval_source=fixture` through:

- API responses.
- UI labels.
- Share cards.
- Export packages.
- Screenshots intended for portfolio use.

Fixture data must not use plausible official URLs in a way that could be mistaken for real records unless the UI and docs clearly label the dataset as demo-only.

## Incomplete Provenance

Use neutral labels:

- Incomplete provenance.
- Source metadata incomplete.
- Parser confidence unavailable.

Avoid labels that imply misconduct, such as unverified wrongdoing or suspicious source.

## Corrections

Corrections must preserve prior state:

- Do not silently overwrite public-facing facts.
- Link superseded filings to replacement filings.
- Show correction or supersession state in detail views.
- Keep raw source documents immutable once archived.

## Share Cards

Every generated card must include:

- Dataset version.
- Methodology version.
- Generated timestamp.
- Source links where available.
- Fixture/demo label when applicable.
- Disclaimer that no causation, legal conclusion, ethics finding, or investment conclusion is being made.
