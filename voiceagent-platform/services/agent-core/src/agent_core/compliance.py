"""Regulatory call-opening disclosure for regulated tenants.

RBI's guidance on AI/voice bots in banking (and India's DPDP Act 2023 more
generally) requires an automated calling assistant to identify itself as
automated and disclose that the call may be recorded, before the
substantive conversation starts — and for that to be an auditable,
timestamped record, not a line in a policy document. This module is that
disclosure, produced as an actual call-opening turn plus a logged event,
gated on the tenant's compliance mode rather than applied globally (a
non-regulated tenant's greeting shouldn't be forced through a banking
disclosure script).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

_REGULATED_COMPLIANCE_MODES = frozenset({"banking"})

_DISCLOSURE_TEXT_BY_LANGUAGE = {
    "en-IN": (
        "This call may be recorded for quality, training, and regulatory "
        "purposes. You are speaking with an automated assistant."
    ),
    "hi-IN": (
        "गुणवत्ता, प्रशिक्षण और नियामक उद्देश्यों के लिए इस कॉल को रिकॉर्ड किया जा "
        "सकता है। आप एक स्वचालित सहायक से बात कर रहे हैं।"
    ),
}
_DEFAULT_DISCLOSURE_LANGUAGE = "en-IN"


@dataclass(frozen=True)
class DisclosureEvent:
    channel_id: str
    tenant_id: str
    timestamp: str  # ISO 8601, UTC


class CompliancePolicy:
    def __init__(self, regulated_modes: frozenset[str] = _REGULATED_COMPLIANCE_MODES):
        self._regulated_modes = regulated_modes

    def requires_disclosure(self, compliance_mode: str) -> bool:
        return compliance_mode in self._regulated_modes

    def disclosure_text(self, language: str) -> str:
        return _DISCLOSURE_TEXT_BY_LANGUAGE.get(language, _DISCLOSURE_TEXT_BY_LANGUAGE[_DEFAULT_DISCLOSURE_LANGUAGE])

    def build_disclosure_event(self, *, channel_id: str, tenant_id: str, now=None) -> DisclosureEvent:
        timestamp = (now or datetime.now(UTC)).isoformat()
        return DisclosureEvent(channel_id=channel_id, tenant_id=tenant_id, timestamp=timestamp)
