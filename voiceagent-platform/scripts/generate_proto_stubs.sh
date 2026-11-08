#!/usr/bin/env bash
# Regenerates gRPC stubs from shared/proto into each consuming service.
# Python services use grpc_tools.protoc; orchestration-api loads the
# .proto file directly at runtime via @grpc/proto-loader, so no
# generation step is needed there.
set -euo pipefail

PROTO_DIR="shared/proto"

for svc in telephony-gateway voice-pipeline agent-core; do
  OUT_DIR="services/${svc}/src/$(echo "$svc" | tr '-' '_')/generated"
  mkdir -p "$OUT_DIR"
  python -m grpc_tools.protoc \
    -I "$PROTO_DIR" \
    --python_out="$OUT_DIR" \
    --grpc_python_out="$OUT_DIR" \
    "$PROTO_DIR"/*.proto
  echo "Generated stubs for $svc into $OUT_DIR"
done
