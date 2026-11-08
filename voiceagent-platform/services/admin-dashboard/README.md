# admin-dashboard

Internal ops console: tenant configuration, live call monitoring, and
transcript QA. Talks only to orchestration-api, never directly to the
voice or telephony services.

This is currently a minimal shell. Build out views under `src/` as
orchestration-api's tenant and session endpoints firm up.
