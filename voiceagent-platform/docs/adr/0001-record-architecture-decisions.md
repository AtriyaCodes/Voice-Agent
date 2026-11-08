# 1. Record architecture decisions

## Status
Accepted

## Context
VoiceAgent makes a number of stack and boundary decisions (language split,
telephony stack, tenancy model, PCI isolation) that are easy to
relitigate without a written record of why they were made.

## Decision
Use lightweight Architecture Decision Records in `docs/adr/`, one per
significant decision, numbered sequentially. Superseding a decision
means adding a new ADR that references the old one, not editing the old
one in place.

## Consequences
Anyone joining the project can read `docs/adr/` in order and understand
both the current architecture and why it is not some other, equally
plausible architecture.
