from app.parsers.base import DisclosureParser, ParserPreview


class PreviewOnlyParser(DisclosureParser):
    def __init__(self, source_id: str, document_type: str, branch: str):
        self.source_id = source_id
        self.document_type = document_type
        self.branch = branch

    def preview(self, content: bytes, *, filename: str, content_type: str) -> ParserPreview:
        text_sample = ""
        try:
            text_sample = content[:500].decode("utf-8", errors="ignore").strip()
        except Exception:
            text_sample = ""

        warnings = [
            "Preview-only parser: raw artifact archived, but normalized records were not promoted.",
            "Human review is required before creating public-facing filings or trades.",
        ]
        if not text_sample and content_type.startswith("application/pdf"):
            warnings.append("PDF text extraction is not implemented in the preview adapter.")

        return ParserPreview(
            source_id=self.source_id,
            document_type=self.document_type,
            normalized_record_count=0,
            warnings=warnings,
            output={
                "branch": self.branch,
                "filename": filename,
                "content_type": content_type,
                "byte_count": len(content),
                "text_sample": text_sample,
            },
        )


PARSERS = {
    "house-financial-disclosure": PreviewOnlyParser(
        "house-financial-disclosure", "legislative_financial_disclosure", "Legislative"
    ),
    "senate-public-financial-disclosure": PreviewOnlyParser(
        "senate-public-financial-disclosure", "legislative_financial_disclosure", "Legislative"
    ),
    "oge-individual-disclosures": PreviewOnlyParser(
        "oge-individual-disclosures", "executive_financial_disclosure", "Executive"
    ),
    "judicial-financial-disclosure": PreviewOnlyParser(
        "judicial-financial-disclosure", "judicial_financial_disclosure", "Judicial"
    ),
}


def get_supported_source_ids() -> list[str]:
    return sorted(PARSERS)


def get_parser(source_id: str) -> DisclosureParser:
    try:
        return PARSERS[source_id]
    except KeyError as exc:
        supported = ", ".join(get_supported_source_ids())
        raise ValueError(f"Unsupported source_id '{source_id}'. Supported: {supported}") from exc
