Place `pjsip.conf`, `extensions.conf`, and `ari.conf` here for local
development. These are deployment specific (trunk credentials, dialplan
routing to the Stasis app) and are intentionally not checked in with
real values; use `.env.example` as the pattern and keep real trunk
credentials out of version control entirely.
