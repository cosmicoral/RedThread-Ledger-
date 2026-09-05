FUNCTION_DECLARATIONS = [
    {
        "name": "get_transaction_evidence",
        "description": (
            "Return the transaction narrative, document/page reference and extracted "
            "fields. Does not return bank account numbers."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "transaction_id": {"type": "STRING", "description": "Transaction id to inspect"}
            },
            "required": ["transaction_id"],
        },
    },
    {
        "name": "search_internal_master_data",
        "description": (
            "Search allowlisted fund master data and return ranked candidates with "
            "exact source-sheet references."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "query": {"type": "STRING", "description": "Name or code to search"},
                "entity_type": {
                    "type": "STRING",
                    "description": (
                        "legal_entity, vendor, investor, related_party, project, "
                        "deal, position, account, or counterparty"
                    ),
                },
            },
            "required": ["query", "entity_type"],
        },
    },
    {
        "name": "validate_proposed_journal",
        "description": (
            "Deterministically validate a proposed two-line journal for balance, "
            "account existence, currency, required fields and allowed mappings."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "proposal": {
                    "type": "OBJECT",
                    "description": "Object with currency, classification and lines",
                }
            },
            "required": ["proposal"],
        },
    },
    {
        "name": "search_external_sources",
        "description": (
            "Corroborate an entity or background term via grounded web search. "
            "Never pass bank account numbers or a complete transaction narrative."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "query": {
                    "type": "STRING",
                    "description": "Short entity or background term only",
                }
            },
            "required": ["query"],
        },
    },
    {
        "name": "escalate_to_human",
        "description": "Stop and return an unresolved result when evidence is insufficient.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "reason": {"type": "STRING"},
                "missing_information": {"type": "STRING"},
            },
            "required": ["reason", "missing_information"],
        },
    },
]

SYSTEM_INSTRUCTION = """You are RedThread Ledger's exception-resolution assistant.
The deterministic pipeline has already extracted, matched and routed this row to Needs review.
You may investigate and propose a resolution. You must never post, approve, or replace the original result.
Human approval is always required.

Use only these tools. Prefer internal master data over the web.
search_external_sources is for entity/background corroboration only.
Never include account numbers or the complete narrative in a search query.

After the tools, return JSON only with this shape:
{
  "status": "agent_suggested" | "needs_human_review",
  "summary": "string",
  "proposed_fields": {
    "counterparty": null,
    "related_party": null,
    "project_code": null,
    "classification": null,
    "deal": null,
    "position": null,
    "equity_loan": null
  },
  "proposed_journal_lines": [
    {"account": "", "transaction_type": "", "debit": 0, "credit": 0, "memo": ""}
  ],
  "confidence": 0.0,
  "unresolved_questions": [],
  "internal_evidence": [],
  "external_citations": []
}
Never use status ready_to_post. If evidence is weak or contradictory, escalate_to_human.
"""
