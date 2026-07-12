import csv
import hashlib
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
HOUSE_ACTIONS = {"P": "BUY", "S": "SELL", "E": "EXCHANGE"}
FIELD_ALIASES = {
    "owner": {"owner", "ownership", "who"},
    "asset": {
        "asset",
        "asset_name",
        "description",
        "security",
        "name_of_asset",
        "identification_of_assets",
    },
    "ticker": {"ticker", "symbol", "ticker_symbol"},
    "action": {"action", "transaction_type", "type", "type_of_transaction"},
    "date": {"date", "transaction_date", "date_of_transaction"},
    "amount": {"amount", "value", "range", "amount_of_transaction"},
    "comment": {"comment", "comments", "notes", "description_of_transaction"},
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
    if lowered in {"p", "purchase (partial)", "purchase (full)"}:
        return "BUY"
    if lowered in {"s", "s (partial)", "s (full)", "sale (partial)", "sale (full)"}:
        return "SELL"
    if lowered in {"e", "exchange (partial)", "exchange (full)"}:
        return "EXCHANGE"
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
    metadata: dict = {"source_metadata_fields": {}}
    patterns = {
        "filer_name": r"^(?:filer|name|name of reporting individual)\s*[:\-]\s*(.+)$",
        "report_type": r"^(?:report type|filing type|form|type of report)\s*[:\-]\s*(.+)$",
        "filing_date": r"^(?:filing date|filed|date filed|date of filing)\s*[:\-]\s*(.+)$",
        "agency": r"^(?:agency|department|office)\s*[:\-]\s*(.+)$",
        "position": r"^(?:position|title|position title)\s*[:\-]\s*(.+)$",
        "court": r"^(?:court|judicial station)\s*[:\-]\s*(.+)$",
        "reporting_period": r"^(?:reporting period|period covered)\s*[:\-]\s*(.+)$",
        "report_year": r"^(?:report year|calendar year)\s*[:\-]\s*(.+)$",
        "report_status": r"^(?:report status|status)\s*[:\-]\s*(.+)$",
    }
    for key, pattern in patterns.items():
        match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
        if match:
            value = clean(match.group(1))
            if key == "filing_date" and value:
                date_match = DATE_RE.search(value)
                value = normalize_date(date_match.group(1)) if date_match else value
            metadata[key] = value
            metadata["source_metadata_fields"][key] = clean(match.group(0))
    metadata["is_amendment"] = bool(
        re.search(r"\b(?:amended|amendment)\b", " ".join(
            str(metadata.get(key) or "") for key in ("report_type", "report_status")
        ), re.IGNORECASE)
    )
    return metadata


def normalize_field_name(value: str) -> str:
    return re.sub(r"_+", "_", re.sub(r"[^a-z0-9]+", "_", value.strip().lower())).strip("_")


def canonical_field_map(fieldnames: list[str | None]) -> dict[str, str]:
    canonical = {}
    for field in fieldnames:
        if not field:
            continue
        normalized = normalize_field_name(field)
        for target, aliases in FIELD_ALIASES.items():
            if normalized in aliases:
                canonical[field] = target
                break
    return canonical


def deterministic_transaction_signature(transaction: ParsedTransaction | dict) -> str:
    if isinstance(transaction, ParsedTransaction):
        values = transaction.to_dict()
        values["transaction_date"] = transaction.transaction_date
        values["transaction_type"] = transaction.transaction_type
        values["amount"] = transaction.amount
    else:
        values = transaction
    identity = "|".join(
        re.sub(r"\s+", " ", str(values.get(key) or "").strip()).casefold()
        for key in ("owner", "asset", "ticker", "transaction_type", "transaction_date", "amount")
    )
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()


def detect_delimited_table(text: str) -> tuple[int, str] | None:
    aliases = set().union(*FIELD_ALIASES.values())
    for index, line in enumerate(text.splitlines()):
        for delimiter in ("\t", ",", "|"):
            if delimiter not in line:
                continue
            fields = [normalize_field_name(value) for value in next(csv.reader([line], delimiter=delimiter))]
            recognized = sum(field in aliases for field in fields)
            if recognized >= 3 and any(field in FIELD_ALIASES["asset"] for field in fields):
                return index, delimiter
    return None


def extract_table_transactions(text: str) -> list[ParsedTransaction]:
    transactions = []
    lines = text.splitlines()
    table = detect_delimited_table(text)
    if table is None:
        return transactions
    header_index, delimiter = table
    reader = csv.DictReader(io.StringIO("\n".join(lines[header_index:])), delimiter=delimiter)
    if not reader.fieldnames:
        return transactions
    normalized_fields = canonical_field_map(reader.fieldnames)
    if "asset" not in normalized_fields.values():
        return transactions

    for row_number, row in enumerate(reader, start=1):
        by_key = {normalized_fields.get(key, normalize_field_name(key or "")): value for key, value in row.items()}
        asset = clean(by_key.get("asset"))
        date = clean(by_key.get("date"))
        amount = clean(by_key.get("amount"))
        action = clean(by_key.get("action"))
        if not asset or not date or not amount or not action:
            continue
        normalized_action = normalize_action(action)
        confidence, field_confidence = transaction_confidence(
            asset=asset,
            date=date,
            amount=amount,
            action=normalized_action,
            ticker=clean(by_key.get("ticker")),
        )
        transactions.append(
            ParsedTransaction(
                owner=clean(by_key.get("owner")),
                asset=asset,
                ticker=clean(by_key.get("ticker")),
                transaction_type=normalized_action,
                transaction_date=normalize_date(date),
                amount=amount,
                comment=clean(by_key.get("comment")),
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
        table = detect_delimited_table(text)
        layout = "delimited_table" if table else "line_or_text_layout"

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
                "record_status": "parser_preview",
                "confidence_label": "Parser preview only",
                "review_required_before_promotion": True,
                "text_sample": text[:1000].strip(),
                "metadata": metadata,
                "source_layout": {
                    "layout": layout,
                    "delimiter": table[1] if table else None,
                    "header_line": table[0] + 1 if table else None,
                },
                "transaction_signatures": [
                    deterministic_transaction_signature(transaction) for transaction in transactions
                ],
                "transactions": [transaction.to_dict() for transaction in transactions],
            },
        )


class OGEFinancialDisclosureParser(SourceSpecificTransactionParser):
    def preview(self, content: bytes, *, filename: str, content_type: str) -> ParserPreview:
        preview = super().preview(content, filename=filename, content_type=content_type)
        metadata = preview.output["metadata"]
        metadata["form_family"] = (
            "OGE Form 278-T" if "278-t" in (metadata.get("report_type") or "").lower()
            else "OGE Form 278e" if "278" in (metadata.get("report_type") or "").lower()
            else "unresolved_oge_form"
        )
        preview.output["source_layout"]["source_layout_family"] = "oge_public_financial_disclosure"
        return preview


class SenateFinancialDisclosureParser(SourceSpecificTransactionParser):
    def preview(self, content: bytes, *, filename: str, content_type: str) -> ParserPreview:
        preview = super().preview(content, filename=filename, content_type=content_type)
        preview.output["source_layout"]["source_layout_family"] = "senate_public_financial_disclosure"
        return preview


class JudicialFinancialDisclosureParser(SourceSpecificTransactionParser):
    def preview(self, content: bytes, *, filename: str, content_type: str) -> ParserPreview:
        preview = super().preview(content, filename=filename, content_type=content_type)
        metadata = preview.output["metadata"]
        report_type = (metadata.get("report_type") or "").lower()
        metadata["form_family"] = "AO 10T" if "10t" in report_type else "AO 10" if "ao 10" in report_type else "unresolved_judicial_form"
        preview.output["source_layout"]["source_layout_family"] = "judiciary_financial_disclosure"
        return preview


def clean_pdf_word(value: str) -> str:
    return re.sub(r"\s+", " ", value.replace("\x00", "")).strip()


def words_in_column(words: list[dict], start: float, end: float, top: float, bottom: float) -> list[dict]:
    return [
        word
        for word in words
        if start <= float(word["x0"]) < end and top <= float(word["top"]) < bottom
    ]


def joined_words(words: list[dict]) -> str | None:
    value = " ".join(clean_pdf_word(word["text"]) for word in sorted(words, key=lambda word: (word["top"], word["x0"])))
    return clean(value)


def house_table_columns(words: list[dict]) -> tuple[dict[str, float], float] | None:
    for owner in words:
        if clean_pdf_word(owner["text"]).lower() != "owner":
            continue
        top = float(owner["top"])
        header = [word for word in words if abs(float(word["top"]) - top) <= 2]

        def x_for(label: str, *, after: float = 0) -> float | None:
            matches = [
                float(word["x0"])
                for word in header
                if clean_pdf_word(word["text"]).lower() == label and float(word["x0"]) > after
            ]
            return min(matches) if matches else None

        owner_x = float(owner["x0"])
        asset_x = x_for("asset", after=owner_x)
        transaction_x = x_for("transaction", after=asset_x or owner_x)
        date_x = x_for("date", after=transaction_x or owner_x)
        notification_x = x_for("notification", after=date_x or owner_x)
        amount_x = x_for("amount", after=notification_x or owner_x)
        cap_x = x_for("cap.", after=amount_x or owner_x) or x_for("cap", after=amount_x or owner_x)
        if all(value is not None for value in [asset_x, transaction_x, date_x, notification_x, amount_x]):
            return (
                {
                    "id": 0,
                    "owner": owner_x,
                    "asset": asset_x,
                    "action": transaction_x,
                    "date": date_x,
                    "notification": notification_x,
                    "amount": amount_x,
                    "cap": cap_x or max(float(word["x1"]) for word in words),
                    "right": max(float(word["x1"]) for word in words) + 1,
                },
                max(float(word["bottom"]) for word in words if abs(float(word["top"]) - top) <= 16),
            )
    return None


def house_footer_top(words: list[dict], header_bottom: float, page_height: float) -> float:
    candidates = []
    for word in words:
        text = clean_pdf_word(word["text"]).lower()
        top = float(word["top"])
        if top <= header_bottom:
            continue
        if (text == "*" and float(word["x0"]) < 45) or text in {"initial", "certification"}:
            candidates.append(top)
        if text == "i" and float(word["x0"]) < 55:
            line = joined_words([item for item in words if abs(float(item["top"]) - top) <= 2]) or ""
            if "certify" in line.lower():
                candidates.append(top)
    return min(candidates) if candidates else page_height


def house_filer_name(words: list[dict]) -> str | None:
    for word in words:
        if clean_pdf_word(word["text"]).lower() != "name:":
            continue
        top = float(word["top"])
        row = [
            item
            for item in words
            if abs(float(item["top"]) - top) <= 2 and float(item["x0"]) > float(word["x1"])
        ]
        return joined_words(row)
    return None


def house_filing_date(text: str) -> str | None:
    match = re.search(r"Digitally Signed:.*?,\s*(\d{1,2}/\d{1,2}/\d{4})", text, re.IGNORECASE)
    return normalize_date(match.group(1)) if match else None


def extract_house_pdf_transactions(content: bytes) -> tuple[list[ParsedTransaction], dict, list[str]]:
    import pdfplumber

    transactions = []
    warnings = []
    filer_name = None
    filing_date = None
    page_count = 0
    embedded_text_character_count = 0
    with pdfplumber.open(io.BytesIO(content)) as document:
        page_count = len(document.pages)
        for page_number, page in enumerate(document.pages, start=1):
            words = page.extract_words(x_tolerance=2, y_tolerance=2)
            text = page.extract_text() or ""
            embedded_text_character_count += len(text.strip())
            filer_name = filer_name or house_filer_name(words)
            filing_date = filing_date or house_filing_date(text)
            table = house_table_columns(words)
            if not table:
                continue
            columns, header_bottom = table
            footer_top = house_footer_top(words, header_bottom, float(page.height))
            date_words = [
                word
                for word in words
                if columns["date"] - 5 <= float(word["x0"]) < columns["notification"] - 5
                and header_bottom < float(word["top"]) < footer_top
                and DATE_RE.fullmatch(clean_pdf_word(word["text"]))
            ]
            for page_row, date_word in enumerate(sorted(date_words, key=lambda word: word["top"]), start=1):
                row_top = float(date_word["top"]) - 2
                following = [float(word["top"]) for word in date_words if float(word["top"]) > float(date_word["top"]) + 2]
                row_bottom = min(following) - 2 if following else footer_top
                asset_words = words_in_column(
                    words, columns["asset"] - 5, columns["action"] - 5, row_top, row_bottom
                )
                asset_lines = []
                for line_top in sorted({round(float(word["top"]), 1) for word in asset_words}):
                    line = joined_words([word for word in asset_words if abs(float(word["top"]) - line_top) <= 0.2])
                    normalized_line = clean_pdf_word(line or "")
                    if re.fullmatch(r"F\s+S:?\s*(New|Amendment)?", normalized_line, re.IGNORECASE):
                        continue
                    if normalized_line:
                        asset_lines.append(normalized_line)
                asset = clean(" ".join(asset_lines))
                action_raw = joined_words(
                    words_in_column(words, columns["action"] - 5, columns["date"] - 5, row_top, row_top + 14)
                )
                amount = joined_words(
                    words_in_column(words, columns["amount"] - 5, columns["cap"] - 5, row_top, row_top + 18)
                )
                owner = joined_words(
                    words_in_column(words, columns["owner"] - 5, columns["asset"] - 5, row_top, row_top + 18)
                )
                notification = joined_words(
                    words_in_column(
                        words,
                        columns["notification"] - 5,
                        columns["amount"] - 5,
                        row_top,
                        row_top + 18,
                    )
                )
                row_id = joined_words(
                    words_in_column(words, columns["id"], columns["owner"] - 5, row_top, row_top + 18)
                )
                action_code = clean_pdf_word(action_raw or "").upper()[:1]
                action = HOUSE_ACTIONS.get(action_code)
                transaction_date = normalize_date(clean_pdf_word(date_word["text"]))
                if not asset or not action or not amount:
                    warnings.append(
                        f"Page {page_number} row {page_row} was not normalized because required columns were incomplete."
                    )
                    continue
                ticker_match = re.search(r"\(([A-Z][A-Z0-9.\-]{0,9})\)", asset)
                ticker = ticker_match.group(1) if ticker_match else None
                confidence, field_confidence = transaction_confidence(
                    asset=asset,
                    date=transaction_date,
                    amount=amount,
                    action=action,
                    ticker=ticker,
                )
                comment_parts = []
                if notification and DATE_RE.search(notification):
                    comment_parts.append(f"Notification date: {normalize_date(DATE_RE.search(notification).group(1))}")
                if row_id:
                    comment_parts.append(f"House row ID: {row_id}")
                transactions.append(
                    ParsedTransaction(
                        owner=owner,
                        asset=asset,
                        ticker=ticker,
                        transaction_type=action,
                        transaction_date=transaction_date,
                        amount=amount,
                        comment="; ".join(comment_parts) or None,
                        row_number=len(transactions) + 1,
                        confidence=confidence,
                        field_confidence={**field_confidence, "source_page": page_number},
                    )
                )
    return transactions, {
        "filer_name": filer_name,
        "filing_date": filing_date,
        "page_count": page_count,
        "embedded_text_character_count": embedded_text_character_count,
        "ocr_required": not transactions and embedded_text_character_count < 80,
    }, warnings


class HouseFinancialDisclosureParser(SourceSpecificTransactionParser):
    def preview(self, content: bytes, *, filename: str, content_type: str) -> ParserPreview:
        if not content_type.startswith("application/pdf") and not filename.lower().endswith(".pdf"):
            return super().preview(content, filename=filename, content_type=content_type)

        transactions, metadata, warnings = extract_house_pdf_transactions(content)
        warnings.extend(
            [
                "Parser preview only: normalized records require explicit review before promotion.",
                "Human review is required before creating public-facing filings or trades.",
            ]
        )
        if not transactions:
            warnings.append("No House PTR transaction rows were detected.")
        return ParserPreview(
            source_id=self.source_id,
            document_type=self.document_type,
            normalized_record_count=len(transactions),
            filer_name=metadata.get("filer_name"),
            report_type="Periodic Transaction Report",
            filing_date=metadata.get("filing_date"),
            transactions=transactions,
            warnings=warnings,
            output={
                "branch": self.branch,
                "filename": filename,
                "content_type": content_type,
                "byte_count": len(content),
                "page_count": metadata.get("page_count"),
                "record_status": "parser_preview",
                "confidence_label": "House Clerk PTR parser preview",
                "review_required_before_promotion": True,
                "extraction_method": "pdfplumber_position_aware_house_ptr_v1",
                "metadata": metadata,
                "source_layout": {
                    "layout": "position_aware_pdf_table",
                    "source_layout_family": "house_clerk_periodic_transaction_report",
                    "page_count": metadata.get("page_count"),
                },
                "transaction_signatures": [
                    deterministic_transaction_signature(transaction) for transaction in transactions
                ],
                "transactions": [transaction.to_dict() for transaction in transactions],
            },
        )


PARSERS = {
    "house-financial-disclosure": HouseFinancialDisclosureParser(
        "house-financial-disclosure", "legislative_financial_disclosure", "Legislative"
    ),
    "senate-public-financial-disclosure": SenateFinancialDisclosureParser(
        "senate-public-financial-disclosure", "legislative_financial_disclosure", "Legislative"
    ),
    "oge-individual-disclosures": OGEFinancialDisclosureParser(
        "oge-individual-disclosures", "executive_financial_disclosure", "Executive"
    ),
    "judicial-financial-disclosure": JudicialFinancialDisclosureParser(
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
