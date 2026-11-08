# infra

- `docker/` holds Dockerfile-adjacent config used only for local dev (Asterisk config).
- `k8s/` holds the base manifests for on-premise or cloud Kubernetes deployment. These are a starting point: production values (replica counts, resource limits, secret names) should move into an overlay (Kustomize or Helm) per environment rather than being edited in place here.

On-premise, air-gapped deployments typically run the same manifests against a customer-managed cluster with an internal image registry mirror; see `docs/adr/` for how model and dependency provisioning is handled without external network access in that mode.
