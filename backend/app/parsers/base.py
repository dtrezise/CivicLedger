from dataclasses import dataclass, field


@dataclass(frozen=True)
class ParsedTransaction:
    owner: str | None
    asset: str
    ticker: str | None
    transaction_type: str
    transaction_date: str
    amount: str
    comment: str | None = None
    row_number: int | None = None

    def to_dict(self) -> dict:
        return {
            "owner": self.owner,
            "asset": self.asset,
            "ticker": self.ticker,
            "transaction_type": self.transaction_type,
            "transaction_date": self.transaction_date,
            "amount": self.amount,
            "comment": self.comment,
            "row_number": self.row_number,
        }


@dataclass(frozen=True)
class ParserPreview:
    source_id: str
    document_type: str
    normalized_record_count: int
    filer_name: str | None = None
    report_type: str | None = None
    filing_date: str | None = None
    transactions: list[ParsedTransaction] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    output: dict = field(default_factory=dict)


class DisclosureParser:
    source_id: str
    document_type: str = "unknown"

    def preview(self, content: bytes, *, filename: str, content_type: str) -> ParserPreview:
        raise NotImplementedError
