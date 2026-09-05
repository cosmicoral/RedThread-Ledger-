from __future__ import annotations

import re

from matching.text import choose_unique, mark_chosen, normalize, rank_matches
from models import MatchCandidate, SourceEvidence, TransactionResult

PROJECT_RE = re.compile(
    r"PROJECT\s+([A-Z0-9][A-Z0-9 /&-]{0,40}?)(?:\s*[).,]|$)",
    re.I,
)
NO_COUNTERPARTY = (
    "COMMISSION",
    "CREDIT INTEREST",
    "CHARGES FOR",
    "BANK CHARGES",
    "CHARGE WAIVED",
)


def _rows(reference_data: dict, sheet: str) -> list[dict[str, str]]:
    return reference_data.get(sheet, [])


def match_legal_entity(row: dict, reference_data: dict) -> tuple[str | None, str | None, list[MatchCandidate]]:
    account_number = row.get("account_number", "")
    bank_account = None
    for item in _rows(reference_data, "Account Map"):
        if item.get("Account Number") == account_number:
            bank_account = item.get("Bank Account")
            break

    query = row.get("account_name") or bank_account or ""
    matches = rank_matches(
        query,
        _rows(reference_data, "Legal Entity Master List"),
        sheet="Legal Entity Master List",
        key_field="Legal Entity",
        field="legal_entity",
    )
    chosen = choose_unique(matches, prefer_simple=True)
    return (chosen.label if chosen else None), bank_account, mark_chosen(matches, chosen)


def pull_project(narrative: str) -> str | None:
    match = PROJECT_RE.search(narrative or "")
    if match:
        return match.group(1).strip(" .)")
    return None


def pull_equity_loan(narrative: str) -> str | None:
    text = (narrative or "").upper()
    if re.search(r"\bEQUITY\b", text):
        return "Equity"
    if re.search(r"\bLOAN\b|\bACC(?:RUED)?\s+INT", text):
        return "Loan"
    return None


def pull_counterparty(narrative: str) -> str | None:
    text = (narrative or "").strip()
    if not text:
        return None
    upper = text.upper()
    if any(token in upper for token in ("COMMISSION", "CREDIT INTEREST", "CHARGES FOR")):
        return None
    if "INTERNAL FX" in upper or "INTERNAL TRANSFER" in upper:
        return None

    cleaned = re.sub(r"^\d[\d, /.-]*\s*,\s*", "", text)
    cleaned = re.sub(r"^\d+/", "", cleaned)
    first = cleaned.split(",")[0].strip()
    if len(first) < 3:
        return None
    if first.upper().startswith("PMT ") or first.upper().startswith("PAYMENT "):
        return None
    return first


def match_project(pulled: str | None, reference_data: dict) -> tuple[str | None, list[MatchCandidate]]:
    if not pulled:
        return None, []
    matches = rank_matches(
        pulled,
        [row for row in _rows(reference_data, "Project Code Report") if row.get("Project Code")],
        sheet="Project Code Report",
        key_field="Project Code",
        field="project_code",
        limit=8,
    )
    exact = [item for item in matches if normalize(item.label) == normalize(pulled)]
    chosen = choose_unique(exact or matches, minimum=0.8, margin=0.15)
    return (chosen.label if chosen else None), mark_chosen(matches, chosen)


def match_counterparty(
    pulled: str | None, reference_data: dict
) -> tuple[str | None, str | None, list[MatchCandidate]]:
    if not pulled:
        return None, None, []
    sources = [
        ("Related Party Master", "Related Party", "related_party"),
        ("Vendor Master List", "Vendor", "vendor"),
        ("Legal Entity Master List", "Legal Entity", "legal_entity"),
        ("Investor Master List", "Investor", "investor"),
    ]
    all_matches: list[MatchCandidate] = []
    for sheet, key, field in sources:
        all_matches.extend(
            rank_matches(pulled, _rows(reference_data, sheet), sheet=sheet, key_field=key, field=field)
        )
    all_matches.sort(key=lambda item: (-item.score, len(item.label)))
    shortlist = all_matches[:8]
    chosen = choose_unique(shortlist, minimum=0.7, margin=0.05)
    related = None
    if chosen and chosen.sheet == "Related Party Master":
        related = chosen.label
    return (chosen.label if chosen else None), related, mark_chosen(shortlist, chosen)


def match_deal_position(
    *,
    legal_entity: str | None,
    project_code: str | None,
    equity_loan: str | None,
    reference_data: dict,
) -> tuple[str | None, str | None, list[MatchCandidate]]:
    if not legal_entity or not project_code:
        return None, None, []
    wanted_type = None
    if equity_loan == "Equity":
        wanted_type = "equity"
    elif equity_loan == "Loan":
        wanted_type = "funding loan"

    candidates: list[MatchCandidate] = []
    for row in _rows(reference_data, "Deal & Position Master List"):
        if row.get("Legal Entity") != legal_entity:
            continue
        blob = " ".join(
            [
                row.get("Deal Name", ""),
                row.get("Position", ""),
                row.get("Issuer Name", ""),
            ]
        )
        if normalize(project_code) not in normalize(blob) and normalize(project_code) not in normalize(
            row.get("Deal Name", "")
        ):
            # allow project token inside deal/position words
            if normalize(project_code) not in normalize(blob).replace(" ", ""):
                deal_tokens = set(normalize(blob).split())
                if normalize(project_code) not in deal_tokens:
                    continue
        security = (row.get("Security Type") or "").lower()
        if wanted_type and wanted_type not in security:
            continue
        position = row.get("Position") or ""
        if "Halstead" in position:
            score = 0.8
        else:
            score = 0.95
        candidates.append(
            MatchCandidate(
                sheet="Deal & Position Master List",
                key=position,
                label=position,
                score=score,
                field="position",
            )
        )
    candidates.sort(key=lambda item: (-item.score, len(item.label)))
    shortlist = candidates[:6]
    chosen = choose_unique(shortlist, minimum=0.75, margin=0.05, prefer_simple=True)
    deal = None
    if chosen:
        for row in _rows(reference_data, "Deal & Position Master List"):
            if row.get("Position") == chosen.label and row.get("Legal Entity") == legal_entity:
                deal = row.get("Deal Name")
                break
    return deal, (chosen.label if chosen else None), mark_chosen(shortlist, chosen)


def match_transaction(row: dict, reference_data: dict) -> TransactionResult:
    legal_entity, bank_account, le_matches = match_legal_entity(row, reference_data)
    pulled_project = pull_project(row.get("narrative", ""))
    project_code, project_matches = match_project(pulled_project, reference_data)
    pulled_counterparty = pull_counterparty(row.get("narrative", ""))
    counterparty, related_party, cp_matches = match_counterparty(pulled_counterparty, reference_data)
    equity_loan = pull_equity_loan(row.get("narrative", ""))
    deal, position, deal_matches = match_deal_position(
        legal_entity=legal_entity,
        project_code=project_code,
        equity_loan=equity_loan,
        reference_data=reference_data,
    )

    candidates = le_matches + project_matches + cp_matches + deal_matches
    chosen_scores = [item.score for item in candidates if item.chosen] or [
        item.score for item in candidates[:1]
    ]

    return TransactionResult(
        transaction_id=row.get("transaction_id", "unknown"),
        date=row.get("date"),
        currency=row.get("currency"),
        amount=row.get("amount"),
        bank_account=bank_account,
        legal_entity=legal_entity,
        pulled_counterparty=pulled_counterparty,
        counterparty=counterparty,
        related_party=related_party,
        pulled_project=pulled_project,
        project_code=project_code,
        equity_loan=equity_loan,
        deal=deal,
        position=position,
        confidence=max(chosen_scores) if chosen_scores else 0.0,
        evidence=SourceEvidence(
            document_name=row.get("document_name", ""),
            page=row.get("page"),
            bank_reference=row.get("bank_reference"),
            customer_reference=row.get("customer_reference"),
            trn_type=row.get("trn_type"),
            narrative=row.get("narrative", ""),
            account_name=row.get("account_name"),
            account_number=row.get("account_number"),
        ),
        candidates=candidates,
    )
