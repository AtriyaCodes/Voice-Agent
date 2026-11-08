from datetime import UTC, datetime

from agent_core.compliance import CompliancePolicy


def test_requires_disclosure_only_for_banking_mode():
    policy = CompliancePolicy()
    assert policy.requires_disclosure("banking") is True
    assert policy.requires_disclosure("standard") is False


def test_disclosure_text_falls_back_to_english_for_unknown_language():
    policy = CompliancePolicy()
    assert "automated assistant" in policy.disclosure_text("fr-FR")
    assert "automated assistant" in policy.disclosure_text("en-IN")


def test_disclosure_text_has_a_hindi_variant():
    policy = CompliancePolicy()
    assert policy.disclosure_text("hi-IN") != policy.disclosure_text("en-IN")


def test_build_disclosure_event_is_timestamped_and_scoped_to_the_call():
    policy = CompliancePolicy()
    fixed_now = datetime(2026, 1, 1, tzinfo=UTC)

    event = policy.build_disclosure_event(channel_id="chan-1", tenant_id="acme", now=fixed_now)

    assert event.channel_id == "chan-1"
    assert event.tenant_id == "acme"
    assert event.timestamp == "2026-01-01T00:00:00+00:00"
