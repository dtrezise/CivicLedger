from dataclasses import dataclass, field


@dataclass(frozen=True)
class ParserPreview:
    source_id: str
    document_type: str
    normalized_record_count: int
    warnings: list[str] = field(default_factory=list)
    output: dict = field(default_factory=dict)


class DisclosureParser:
    source_id: str
    document_type: str = "unknown"

    def preview(self, content: bytes, *, filename: str, content_type: str) -> ParserPreview:
        raise NotImplementedError
