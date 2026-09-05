"""Metrics used for the hackathon evaluation split.

Splits are made at statement level. The ground-truth Staging Sheet and
DIU sheets are never loaded by the production pipeline.
"""

METRIC_AREAS = [
    "statement_extraction",
    "counterparty_resolution",
    "project_resolution",
    "classification",
    "position_resolution",
    "journal_generation",
    "accounting_validity",
    "exception_handling",
    "evidence",
]
