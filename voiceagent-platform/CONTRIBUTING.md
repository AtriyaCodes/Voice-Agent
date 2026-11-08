# Contributing to VoiceAgent

## Branching

- `main` is always deployable.
- `develop` is the integration branch for the current sprint.
- Feature branches: `feature/<short-description>`, cut from `develop`.
- Fix branches for a live issue: `fix/<short-description>`.

## Before opening a PR

1. `make lint` and `make test` pass locally for every service you touched.
2. If you changed `shared/proto` or `shared/schemas`, run `make proto` and commit the regenerated stubs alongside your change.
3. If your change affects latency on the hot voice path (telephony-gateway, voice-pipeline, agent-core's dialogue loop), note the expected impact in the PR description against the budget in `ARCHITECTURE.md`.
4. If your change touches anything in the payment capture path, re-read `compliance/pci/README.md` first; the isolation boundary described there is a hard requirement, not a guideline.

## Commit style

Conventional commits (`feat:`, `fix:`, `refactor:`, `docs:`, `test:`, `chore:`), scoped to the service when it is clear, for example `feat(voice-pipeline): add barge-in support to turn manager`.

## Architecture changes

Any change to a service boundary, the tenancy model, or the telephony stack should come with an ADR in `docs/adr/`, not just a PR description. See `docs/adr/0001-record-architecture-decisions.md`.
