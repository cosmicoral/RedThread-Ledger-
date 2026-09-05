from evaluation.compare import match_key, score_extraction


def test_match_key_uses_account_ref_and_amount() -> None:
    key = match_key(
        {
            "Account Number": "240-149813-030",
            "Bank reference": "10716RS62GWQ",
            "Debit amount": "-301908.7",
        }
    )
    assert key[0] == "240-149813-030"
    assert key[1] == "10716RS62GWQ"
    assert key[2] == 301908.7


def test_extraction_score_requires_core_fields() -> None:
    predicted = {"bank_reference": "NONREF", "currency": "EUR", "amount": -0.44}
    truth = {"Bank reference": "NONREF", "Currency": "EUR", "Debit amount": "-0.44"}
    assert score_extraction(predicted, truth) is True
