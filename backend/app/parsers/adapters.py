import csv
import io
import re
from datetime import datetime

from app.parsers.base import DisclosureParser, ParserPreview, ParsedTransaction


DATE_RE = re.compile(r"\b(\d{1,2}/\d{1,2}/\d{2,4}|\d{4}-\d{2}-\d{2})\b")
AMOUNT_RE = re.compile(
    r"(\$?\d[\d,]*\s*-\s*\$?\d[\d,]*|\$?\d[\d,]*\+?|Over\s+\$?\d[\d,]*)",
    re.IGNORECASE,
)
ACTION_WORDS = {
    "purchase": "BUY",
    "purchased": "BUY",
    "buy": "BUY",
    "sale": "SELL",
    "sold": "SELL",
    "sell": "SELL",
    "exchange": "EXCHANGE",
    "exchanged": "EXCHANGE",
}


def normalize_date(value: str) -> str:
    value = value.strip()
    if "-" in value:
        return value
    for fmt in ("%m/%d/%Y", "%m/%d/%y"):
        try:
            return datetime.strptime(value, fmt).date().isoformat()
        except ValueError:
            continue
    return value


def normalize_action(value: str) -> str:
    lowered = value.strip().lower()
    for token, normalized in ACTION_WORDS.items():
        if token in lowered:
            return normalized
    return value.strip().upper() or "OTHER"


def extract_text(content: bytes, *, content_type: str) -> tuple[str, list[str]]:
    warnings = []
    if content_type.startswith("application/pdf"):
        try:
            from pypdf import PdfReader

            reader = PdfReader(io.BytesIO(content))
            pages = [page.extract_text() or "" for page in reader.pages]
            return "\n".join(pages), warnings
        except Exception as exc:
            warnings.append(f"PDF text extraction failed; falling back to byte decode: {exc}")

    return content.decode("utf-8", errors="ignore"), warnings


def clean(value: str | None) -> str | None:
    if value is None:
        return None
    value = re.sub(r"\s+", " ", value.strip())
    return value or None


def transaction_confidence(
    *, asset: str | None, date: str | None, amount: str | None, action: str | None, ticker: str | None
) -> tuple[float, dict[str, float]]:
    field_confidence = {
        "asset": 0.95 if asset else 0.0,
        "transaction_date": 0.95 if date else 0.0,
        "amount": 0.9 if amount else 0.0,
        "transaction_type": 0.9 if action in {"BUY", "SELL", "EXCHANGE", "OTHER"} else 0.45,
        "ticker": 0.8 if ticker else 0.35,
    }
    required = ["asset", "transaction_date", "amount", "transaction_type"]
    confidence = sum(field_confidence[field] for field in required) / len(required)
    return round(confidence, 2), field_confidence


def extract_metadata(text: str) -> dict:
    metadata = {}
    patterns = {
        "filer_name": r"(?:filer|name)\s*[:\-]\s*(.+)",
        "report_type": r"(?:report type|filing type|form)\s*[:\-]\s*(.+)",
        "filing_date": r"(?:filing date|filed|date filed)\s*[:\-]\s*(.+)",
    }
    for key, pattern in patterns.items():
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            value = clean(match.group(1).splitlines()[0])
            if key == "filing_date" and value:
                date_match = DATE_RE.search(value)
                value = normalize_date(date_match.group(1)) if date_match else value
            metadata[key] = value
    return metadata


def extract_table_transactions(text: str) -> list[ParsedTransaction]:
    transactions = []
    lines = text.splitlines()
    header_index = 0
    for index, line in enumerate(lines):
        normalized = line.lower()
        if "," in line and any(token in normalized for token in ["asset", "security", "description"]):
            header_index = index
            break

    reader = csv.DictReader(io.StringIO("\n".join(lines[header_index:])))
    if not reader.fieldnames:
        return transactions

    normalized_fields = {
        field: field.strip().lower().replace(" ", "_").replace("-", "_")
        for field in reader.fieldnames
        if field
    }
    desired = set(normalized_fields.values())
    if not desired.intersection({"asset", "asset_name", "security", "description"}):
        return transactions

    for row_number, row in enumerate(reader, start=1):
        by_key = {normalized_fields.get(k, k): v for k, v in row.items()}
        asset = clean(
            by_key.get("asset")
            or by_key.get("asset_name")
            or by_key.get("security")
            or by_key.get("description")
        )
        date = clean(
            by_key.get("transaction_date")
            or by_key.get("date")
            or by_key.get("date_of_transaction")
        )
        amount = clean(by_key.get("amount") or by_key.get("value") or by_key.get("range"))
        action = clean(
            by_key.get("transaction_type") or by_key.get("type") or by_key.get("action")
        )
        if not asset or not date or not amount or not action:
            continue
        normalized_action = normalize_action(action)
        confidence, field_confidence = transaction_confidence(
            asset=asset,
            date=date,
            amount=amount,
            action=normalized_action,
            ticker=clean(by_key.get("ticker") or by_key.get("symbol")),
        )
        transactions.append(
            ParsedTransaction(
                owner=clean(by_key.get("owner")),
                asset=asset,
                ticker=clean(by_key.get("ticker") or by_key.get("symbol")),
                transaction_type=normalized_action,
                transaction_date=normalize_date(date),
                amount=amount,
                comment=clean(by_key.get("comment") or by_key.get("notes")),
                row_number=row_number,
                confidence=confidence,
                field_confidence=field_confidence,
            )
        )
    return transactions


def extract_line_transactions(text: str) -> list[ParsedTransaction]:
    transactions = []
    for row_number, line in enumerate(text.splitlines(), start=1):
        line = clean(line)
        if not line:
            continue
        date_match = DATE_RE.search(line)
        amount_match = AMOUNT_RE.search(line)
        action = next((normalized for token, normalized in ACTION_WORDS.items() if token in line.lower()), None)
        if not date_match or not amount_match or not action:
            continue

        before_date = line[: date_match.start()].strip(" ,-;|")
        after_amount = line[amount_match.end() :].strip(" ,-;|")
        asset = before_date
        ticker = None
        ticker_match = re.search(r"\(([A-Z]{1,6})\)", asset)
        if ticker_match:
            ticker = ticker_match.group(1)
            asset = clean(asset.replace(ticker_match.group(0), "")) or asset
        confidence, field_confidence = transaction_confidence(
            asset=asset,
            date=date_match.group(1),
            amount=amount_match.group(1),
            action=action,
            ticker=ticker,
        )

        transactions.append(
            ParsedTransaction(
                owner=None,
                asset=asset,
                ticker=ticker,
                transaction_type=action,
                transaction_date=normalize_date(date_match.group(1)),
                amount=amount_match.group(1),
                comment=after_amount or None,
                row_number=row_number,
                confidence=confidence,
                field_confidence=field_confidence,
            )
        )
    return transactions


class SourceSpecificTransactionParser(DisclosureParser):
    def __init__(self, source_id: str, document_type: str, branch: str):
        self.source_id = source_id
        self.document_type = document_type
        self.branch = branch

    def preview(self, content: bytes, *, filename: str, content_type: str) -> ParserPreview:
        text, warnings = extract_text(content, content_type=content_type)
        metadata = extract_metadata(text)
        transactions = extract_table_transactions(text) or extract_line_transactions(text)

        warnings.extend([
            "Parser preview only: normalized records require explicit review before promotion.",
            "Human review is required before creating public-facing filings or trades.",
        ])
        if not transactions:
            warnings.append("No transaction rows were detected by the source-specific parser.")

        return ParserPreview(
            source_id=self.source_id,
            document_type=self.document_type,
            normalized_record_count=len(transactions),
            filer_name=metadata.get("filer_name"),
            report_type=metadata.get("report_type"),
            filing_date=metadata.get("filing_date"),
            transactions=transactions,
            warnings=warnings,
            output={
                "branch": self.branch,
                "filename": filename,
                "content_type": content_type,
                "byte_count": len(content),
                "text_sample": text[:1000].strip(),
                "metadata": metadata,
                "transactions": [transaction.to_dict() for transaction in transactions],
            },
        )


PARSERS = {
    "house-financial-disclosure": SourceSpecificTransactionParser(
        "house-financial-disclosure", "legislative_financial_disclosure", "Legislative"
    ),
    "senate-public-financial-disclosure": SourceSpecificTransactionParser(
        "senate-public-financial-disclosure", "legislative_financial_disclosure", "Legislative"
    ),
    "oge-individual-disclosures": SourceSpecificTransactionParser(
        "oge-individual-disclosures", "executive_financial_disclosure", "Executive"
    ),
    "judicial-financial-disclosure": SourceSpecificTransactionParser(
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
