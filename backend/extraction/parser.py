from __future__ import annotations

import re
from datetime import datetime

MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
DATE_TOKEN = r"\d{1,2}\s+(?:" + "|".join(MONTHS) + r")\s+\d{4}"
AMOUNT = r"-?[\d,]+(?:\.\d+)?"

LINE_END = re.compile(
    rf"(?P<value_date>{DATE_TOKEN})\s+"
    rf"(?P<signed>{AMOUNT})\s+"
    rf"(?P<balance>{AMOUNT})\s+"
    rf"(?P<time>\d{{2}}:\d{{2}})\s+"
    rf"(?P<post_date>{DATE_TOKEN})\s*$"
)
DATE_LINE = re.compile(rf"^{DATE_TOKEN}$")
TIME_LINE = re.compile(r"^\d{2}:\d{2}$")
AMOUNT_LINE = re.compile(rf"^{AMOUNT}$")

TRN_TYPES = (
    "TFR+ INT",
    "S+P- CHG",
    "S+P+",
    "S+P-",
    "TFR+",
    "TFR-",
    "SCT",
)

SKIP_PREFIXES = (
    "statement details",
    "account name",
    "account number",
    "bank name",
    "currency",
    "location",
    "bic ",
    "iban ",
    "account status",
    "account type",
    "closing ledger",
    "closing available",
    "current ledger",
    "current available",
    "specified date",
    "from ",
    "as at",
    "bank reference customer reference",
    "balance as at",
    "balance brought forward",
    "page ",
)

COLUMN_HEADERS = {
    "bank reference",
    "customer reference",
    "trn type",
    "value date",
    "credit amount",
    "debit amount",
    "balance",
    "time",
    "post date",
    "statement details",
}

HEADER_LABELS = {
    "account name": "account_name",
    "account number": "account_number",
    "currency": "currency",
}

HEADER_ACCOUNT_NAME = re.compile(r"Account name\s+(.+)", re.I)
HEADER_ACCOUNT_NUMBER = re.compile(r"Account number\s+([0-9-]+)", re.I)
HEADER_CURRENCY = re.compile(r"Currency\s+([A-Z]{3})", re.I)
PAGE_MARK = re.compile(r"Page\s+(\d+)\s+of\s+(\d+)", re.I)


def parse_amount(value: str) -> float:
    return float(value.replace(",", ""))


def parse_date(value: str) -> str:
    return datetime.strptime(value, "%d %b %Y").strftime("%Y-%m-%d")


def _is_skip_line(line: str) -> bool:
    lowered = line.lower()
    if PAGE_MARK.search(line) and "|" in line:
        return True
    return any(lowered.startswith(prefix) for prefix in SKIP_PREFIXES)


def _split_prefix(prefix: str) -> tuple[str, str, str]:
    compact = " ".join(prefix.split())
    trn_type = ""
    remainder = compact
    for candidate in TRN_TYPES:
        if compact.endswith(candidate):
            trn_type = candidate
            remainder = compact[: -len(candidate)].rstrip()
            break
        marker = f" {candidate}"
        if marker in compact:
            idx = compact.rfind(marker)
            trn_type = compact[idx + 1 :]
            remainder = compact[:idx].rstrip()
            break
    parts = remainder.split()
    if not parts:
        return "", "", trn_type
    bank_reference = parts[0]
    customer_reference = " ".join(parts[1:]) if len(parts) > 1 else ""
    return bank_reference, customer_reference, trn_type


def parse_header(text: str) -> dict[str, str]:
    header: dict[str, str] = {}
    if match := HEADER_ACCOUNT_NAME.search(text):
        header["account_name"] = match.group(1).strip()
    if match := HEADER_ACCOUNT_NUMBER.search(text):
        header["account_number"] = match.group(1).strip()
    if match := HEADER_CURRENCY.search(text):
        header["currency"] = match.group(1).strip()
    return header


def _row(
    *,
    document_name: str,
    page_number: int,
    header: dict[str, str],
    bank_reference: str,
    customer_reference: str,
    trn_type: str,
    value_date: str,
    post_date: str,
    signed: float,
    balance: float,
    narrative: str,
) -> dict:
    return {
        "transaction_id": (
            f"{document_name}:{page_number}:{bank_reference}:{value_date}:{signed}"
        ),
        "document_name": document_name,
        "page": page_number,
        "account_name": header.get("account_name", ""),
        "account_number": header.get("account_number", ""),
        "currency": header.get("currency", ""),
        "bank_reference": bank_reference,
        "customer_reference": customer_reference,
        "trn_type": trn_type,
        "date": parse_date(value_date),
        "post_date": parse_date(post_date),
        "amount": signed,
        "balance": balance,
        "narrative": narrative,
    }


def parse_horizontal_pages(
    pages: list[tuple[int, str]],
    document_name: str,
) -> list[dict]:
    header: dict[str, str] = {}
    rows: list[dict] = []
    pending_prefix = ""
    current: dict | None = None

    for page_number, text in pages:
        header.update(parse_header(text))
        for raw in text.splitlines():
            line = raw.strip()
            if not line or line.startswith("--"):
                continue
            if _is_skip_line(line):
                continue
            if line.lower().startswith("narrative") and not LINE_END.search(line):
                narrative = line.split(None, 1)[1] if " " in line else ""
                if current is not None:
                    current["narrative"] = narrative
                pending_prefix = ""
                continue

            match = LINE_END.search(line)
            if match is None:
                pending_prefix = f"{pending_prefix} {line}".strip()
                continue

            prefix = f"{pending_prefix} {line[: match.start()]}".strip()
            pending_prefix = ""
            bank_reference, customer_reference, trn_type = _split_prefix(prefix)
            current = _row(
                document_name=document_name,
                page_number=page_number,
                header=header,
                bank_reference=bank_reference,
                customer_reference=customer_reference,
                trn_type=trn_type,
                value_date=match.group("value_date"),
                post_date=match.group("post_date"),
                signed=parse_amount(match.group("signed")),
                balance=parse_amount(match.group("balance")),
                narrative="",
            )
            rows.append(current)

    return rows


def _looks_vertical(text: str) -> bool:
    return bool(re.search(r"^Narrative\s*$", text, re.M))


def parse_vertical_pages(
    pages: list[tuple[int, str]],
    document_name: str,
) -> list[dict]:
    header: dict[str, str] = {}
    rows: list[dict] = []

    for page_number, text in pages:
        lines = [line.strip() for line in text.splitlines() if line.strip() and line.strip() != "|"]
        i = 0
        while i < len(lines):
            label = lines[i].lower()
            if label in HEADER_LABELS and i + 1 < len(lines):
                header[HEADER_LABELS[label]] = lines[i + 1]
                i += 2
                continue
            i += 1

        def is_window(index: int) -> bool:
            return (
                index + 5 < len(lines)
                and DATE_LINE.match(lines[index]) is not None
                and AMOUNT_LINE.match(lines[index + 1]) is not None
                and AMOUNT_LINE.match(lines[index + 2]) is not None
                and TIME_LINE.match(lines[index + 3]) is not None
                and DATE_LINE.match(lines[index + 4]) is not None
                and lines[index + 5].lower() == "narrative"
            )

        i = 0
        while i < len(lines) and lines[i].lower() != "post date":
            i += 1
        if i < len(lines):
            i += 1

        while i < len(lines):
            lowered = lines[i].lower()
            if (
                lowered in COLUMN_HEADERS
                or lowered in HEADER_LABELS
                or lowered.startswith("page")
                or "|" in lines[i]
                or lowered.startswith("balance")
            ):
                i += 1
                continue
            found = next((k for k in range(i, len(lines)) if is_window(k)), None)
            if found is None:
                break
            prefix = [
                token
                for token in lines[i:found]
                if token.lower() not in COLUMN_HEADERS and token.lower() != "narrative"
            ]
            if prefix:
                bank_reference, customer_reference, trn_type = _split_prefix(" ".join(prefix))
                narrative = lines[found + 6] if found + 6 < len(lines) else ""
                rows.append(
                    _row(
                        document_name=document_name,
                        page_number=page_number,
                        header=header,
                        bank_reference=bank_reference,
                        customer_reference=customer_reference,
                        trn_type=trn_type,
                        value_date=lines[found],
                        post_date=lines[found + 4],
                        signed=parse_amount(lines[found + 1]),
                        balance=parse_amount(lines[found + 2]),
                        narrative=narrative,
                    )
                )
            i = found + 7
    return rows


def parse_statement_pages(
    pages: list[tuple[int, str]],
    document_name: str,
) -> list[dict]:
    combined = "\n".join(text for _, text in pages)
    if _looks_vertical(combined):
        return parse_vertical_pages(pages, document_name)
    return parse_horizontal_pages(pages, document_name)
