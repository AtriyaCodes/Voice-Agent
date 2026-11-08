# 7. telephony-gateway SIP/RTP networking model on Kubernetes

## Status
Accepted

## Context
The original k8s manifests exposed only telephony-gateway's internal gRPC
control port. Nothing exposed SIP (5060/udp) or the RTP media range
(10000-10100/udp in docker-compose) — the actual telephony traffic had no
path into the cluster at all.

This isn't solvable the way the gRPC port is: an ordinary
ClusterIP/NodePort Service load-balances per new connection via
kube-proxy, which is wrong for RTP — a single call's media stream has to
keep landing on the *same* pod for the life of the call, and kube-proxy
has no concept of "this UDP flow belongs to call X."

Three real options exist:
1. **`hostNetwork: true`** — simplest, but a pod fully takes over the
   node's network namespace, and only one such pod can bind 5060/udp per
   node.
2. **A dedicated per-call NodePort/LoadBalancer**, provisioned
   dynamically per call — works, but needs custom automation
   (Kubernetes has no built-in "Service per call") and doesn't fit this
   repo's static-manifest deployment model.
3. **A dedicated RTP relay/SBC in front** (RTPengine, Kamailio) — the
   answer most serious telephony-on-Kubernetes deployments converge on at
   scale: the relay owns the public UDP surface and is built for exactly
   this problem, forwarding decoded media to backend pods over ordinary
   internal networking. telephony-gateway pods go back to being
   unremarkable internally-addressed pods.

## Decision
For this repo's current scale (on-prem/single-tenant-cluster deployments,
not a multi-region carrier-scale platform), use **`hostPort` + pod
anti-affinity** (`infra/k8s/telephony-gateway-deployment.yaml`): each pod
binds SIP and a narrow RTP port range directly on the node it's scheduled
to, and `podAntiAffinity` (topology key `kubernetes.io/hostname`) ensures
only one telephony-gateway pod lands per node, since only one process on
a node can hold 5060/udp. This works in vanilla Kubernetes with no extra
infrastructure — appropriate for where this platform is today — at the
cost of a real constraint: capacity here scales with *node* count, not
pod-per-node density, which is architecturally different from every other
service in this repo.

## Consequences
- The RTP port range in the manifest (10000-10009, 10 concurrent call
  slots per node) is deliberately narrow compared to the docker-compose
  dev range (10000-10100) — each port needs its own `hostPort` entry in
  vanilla k8s, so the range is a capacity/manifest-size trade-off to tune
  per deployment, not a hard architectural limit.
- Scaling telephony-gateway capacity means adding nodes (or moving to
  option 3), not just bumping `replicas` — this should be an explicit
  part of capacity planning conversations, not discovered during a
  traffic spike.
- Once call volume justifies the operational cost of running a dedicated
  media relay, switching to option 3 is the documented upgrade path, and
  it *simplifies* this manifest (telephony-gateway pods drop hostPort and
  anti-affinity entirely) rather than adding to it.
