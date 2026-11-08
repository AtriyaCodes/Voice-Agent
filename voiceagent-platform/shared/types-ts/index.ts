/**
 * Hand-maintained TypeScript mirror of shared/schemas and shared/proto
 * for services that do not generate stubs directly from proto/JSON
 * Schema. Keep this in sync when either source changes; consider
 * generating this file as part of `make proto` once the toolchain is
 * settled.
 */

export interface CallEvent {
  channelId: string;
  tenantId: string;
  eventType:
    | "call_started"
    | "disclosure_acknowledged"
    | "utterance_finalized"
    | "tool_invoked"
    | "degraded"
    | "call_ended"
    | "call_failed";
  timestamp: string;
  metadata?: Record<string, unknown>;
}
