from __future__ import annotations

import re
from collections.abc import Iterable

from models import MatchCandidate

PUNCT = re.compile(r"[^A-Z0-9]+")
ROMANS = frozenset({"I", "II", "III", "IV", "V", "VI"})
NOISE = frozenset(
    {
        "FEEDER",
        "BLOCKER",
        "ELIM",
        "ELIMINATIONS",
        "ELIMINATION",
        "GP",
        "QFPF",
        "NON",
        "US",
        "CN",
        "NO",
        "AIV",
        "COMPARTMENT",
        "ACCESS",
    }
)
ABBREV = {
    "NI": "NORDVIK INFRASTRUCTURE",
    "NIP": "NORDVIK INFRASTRUCTURE",
    "ABF": "ADVANCED BIOENERGY FUND",
    "GMF": "GROWTH MARKETS FUND",
}
SYNONYM = {
    "LUXEMBOURG": "LU",
    "LUX": "LU",
    "LIMITED": "LTD",
    "SARL": "SARL",
    "SA": "SARL",
}


def normalize(value: str) -> str:
    text = value.upper()
    text = (
        text.replace("S.À R.L.", " SARL ")
        .replace("S.A R.L.", " SARL ")
        .replace("S.A R.", " SARL ")
        .replace("P/S", " PS ")
    )
    text = PUNCT.sub(" ", text)
    tokens = [SYNONYM.get(token, token) for token in text.split()]
    return " ".join(tokens)


def expand(value: str) -> str:
    tokens: list[str] = []
    for token in normalize(value).split():
        tokens.extend(ABBREV.get(token, token).split())
    return " ".join(tokens)


def token_set(value: str) -> set[str]:
    return set(expand(value).split())


def score_name(query: str, candidate: str) -> float:
    if not query or not candidate:
        return 0.0
    if normalize(query) == normalize(candidate):
        return 1.0
    query_tokens = token_set(query)
    candidate_tokens = token_set(candidate)
    query_romans = query_tokens & ROMANS
    candidate_romans = candidate_tokens & ROMANS
    if query_romans and candidate_romans and query_romans != candidate_romans:
        return 0.0
    if not query_tokens:
        return 0.0
    overlap = len(query_tokens & candidate_tokens) / len(query_tokens)
    extra_noise = len((candidate_tokens - query_tokens) & NOISE)
    score = max(0.0, overlap - 0.12 * extra_noise)
    # Expanded abbreviation matches are useful but must lose to an exact alias.
    if score >= 0.99:
        return 0.92
    return score


def rank_matches(
    query: str,
    rows: Iterable[dict[str, str]],
    *,
    sheet: str,
    key_field: str,
    field: str,
    limit: int = 5,
) -> list[MatchCandidate]:
    ranked: list[MatchCandidate] = []
    for row in rows:
        label = (row.get(key_field) or "").strip()
        if not label:
            continue
        score = score_name(query, label)
        if score <= 0:
            continue
        ranked.append(
            MatchCandidate(
                sheet=sheet,
                key=label,
                label=label,
                score=round(score, 3),
                field=field,
            )
        )
    ranked.sort(key=lambda item: (-item.score, len(item.label)))
    return ranked[:limit]


def mark_chosen(
    matches: list[MatchCandidate], chosen: MatchCandidate | None
) -> list[MatchCandidate]:
    if chosen is None:
        return matches
    for item in matches:
        item.chosen = (
            item.sheet == chosen.sheet
            and item.key == chosen.key
            and item.field == chosen.field
        )
    return matches


def choose_unique(
    matches: list[MatchCandidate],
    *,
    minimum: float = 0.72,
    margin: float = 0.08,
    prefer_simple: bool = False,
) -> MatchCandidate | None:
    viable = [item for item in matches if item.score >= minimum]
    if not viable:
        return None
    if prefer_simple:
        top = viable[0].score
        close = [item for item in viable if top - item.score <= 0.16]
        close.sort(key=lambda item: (len(token_set(item.label) & NOISE), len(item.label), -item.score))
        return close[0].model_copy(update={"chosen": True})
    if len(viable) > 1 and viable[0].score - viable[1].score < margin:
        if normalize(viable[0].label) != normalize(viable[1].label):
            return None
    return viable[0].model_copy(update={"chosen": True})
