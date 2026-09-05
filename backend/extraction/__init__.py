from pathlib import Path

from pypdf import PdfReader

from extraction.parser import parse_statement_pages


def extract_transactions(pdf_path: Path) -> list[dict]:
    """Extract statement rows from a digital bank-statement PDF."""
    reader = PdfReader(str(pdf_path))
    pages = [
        (index, page.extract_text() or "")
        for index, page in enumerate(reader.pages, start=1)
    ]
    return parse_statement_pages(pages, document_name=pdf_path.name)
