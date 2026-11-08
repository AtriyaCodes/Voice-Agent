from agent_core.redaction import redact_metadata, redact_text


def test_redacts_an_otp_shaped_number():
    assert redact_text("your OTP is 482913") == "your OTP is [redacted:otp-like]"


def test_redacts_a_long_account_number():
    assert redact_text("account number 1234 5678 9012") == "account number [redacted:number]"


def test_leaves_ordinary_text_alone():
    assert redact_text("I need to check my balance please") == "I need to check my balance please"


def test_redact_metadata_recurses_through_nested_structures():
    metadata = {
        "note": "caller confirmed OTP 118204",
        "nested": {"account": "9988776655"},
        "list_field": ["OTP was 552011", "no digits here"],
        "count": 3,
    }

    redacted = redact_metadata(metadata)

    assert redacted["note"] == "caller confirmed OTP [redacted:otp-like]"
    assert redacted["nested"]["account"] == "[redacted:number]"
    assert redacted["list_field"][0] == "OTP was [redacted:otp-like]"
    assert redacted["list_field"][1] == "no digits here"
    assert redacted["count"] == 3  # non-string values pass through untouched


def test_redact_metadata_handles_none():
    assert redact_metadata(None) is None
