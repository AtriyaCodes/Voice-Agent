# 2. SIP telephony stack choice

## Status
Accepted

## Context
telephony-gateway needs to answer inbound SIP calls, bridge media, and
support both carrier SIP trunking and integration with a customer's
existing contact center platform over SIP (as with the ContosoIP
integration). The two realistic open-source options are Asterisk (via
ARI) and FreeSWITCH (via ESL).

## Decision
Default to Asterisk ARI as the reference implementation in this
repository (`sip_handler.py` is written against ARI's event model), with
the SIP handling logic kept behind a thin interface so a FreeSWITCH ESL
implementation can be swapped in per deployment without touching
voice-pipeline or agent-core. Some customer environments (existing
FreeSWITCH-based contact centers) may specifically require the
FreeSWITCH path.

## Consequences
- Local dev and CI default to Asterisk (see `docker-compose.yml`).
- A FreeSWITCH implementation of the same interface can live alongside
  `sip_handler.py` as an alternative, selected per deployment via
  configuration, rather than as a fork of this service.
