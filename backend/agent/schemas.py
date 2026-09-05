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
                    "description": "Object with currency, classification and two journal lines",
                    "properties": {
                        "currency": {
                            "type": "STRING",
                            "description": "ISO currency code from the source transaction",
                        },
                        "classification": {
                            "type": "STRING",
                            "description": "Allowed classification such as Vendor or Related Party",
                        },
                        "lines": {
                            "type": "ARRAY",
                            "description": "Exactly two journal-line objects",
                            "items": {
                                "type": "OBJECT",
                                "properties": {
                                    "account": {
                                        "type": "STRING",
                                        "description": "Account code from the chart of accounts",
                                    },
                                    "transaction_type": {
                                        "type": "STRING",
                                        "description": "Journal transaction type",
                                    },
                                    "debit": {
                                        "type": "NUMBER",
                                        "description": "Debit amount",
                                    },
                                    "credit": {
                                        "type": "NUMBER",
                                        "description": "Credit amount",
                                    },
                                    "memo": {
                                        "type": "STRING",
                                        "description": "Short line memo",
                                    },
                                },
                                "required": [
                                    "account",
                                    "transaction_type",
                                    "debit",
                                    "credit",
                                ],
                            },
                        },
                    },
                    "required": ["currency", "classification", "lines"],
                }
            },
            "required": ["proposal"],
        },
    },
    {
        "name": "search_external_sources",
        "description": (
            "Corroborate a named entity via grounded web search. Pass structured "
            "fields only. Do not pass a query string, narrative, account number, "
            "amount, date, or transaction reference. The server builds the search."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "entity_name": {
                    "type": "STRING",
                    "description": "Short organisation or person name, letters first",
                },
                "entity_type": {
                    "type": "STRING",
                    "description": "vendor, legal_entity, investor, related_party, project, or counterparty",
                },
                "jurisdiction": {
                    "type": "STRING",
                    "description": "Optional country or region name, letters only",
                },
                "project_name": {
                    "type": "STRING",
                    "description": "Optional project or deal name",
                },
            },
            "required": ["entity_name", "entity_type"],
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
Call it with entity_name and entity_type only. Never pass query, account numbers,
amounts, dates, transaction references, or the complete narrative.
Do not author citation URLs. Citations come from grounding metadata.

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
