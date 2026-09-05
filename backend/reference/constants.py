"""Allowlisted reference sheets. Ground-truth names live only here."""

ALLOWED_SHEETS: dict[str, str] = {
    "Account Map": "account-map.csv",
    "Legal Entity Master List": "legal-entity-master-list.csv",
    "Investor Master List": "investor-master-list.csv",
    "Vendor Master List": "vendor-master-list.csv",
    "Vendor Codes": "vendor-codes.csv",
    "Related Party Master": "related-party-master.csv",
    "Project Code Report": "project-code-report.csv",
    "Deal & Position Master List": "deal-position-master-list.csv",
    "CoA": "coa.csv",
    "Allocation Rule": "allocation-rule.csv",
    "Bank Account Report": "bank-account-report.csv",
    "Korean and Taiwanese": "korean-and-taiwanese.csv",
}

# Names the runtime must never open. Keep this the only backend mention.
FORBIDDEN_SHEETS: frozenset[str] = frozenset(
    {
        "Staging Sheet",
        "DIU",
        "Process",
    }
)
