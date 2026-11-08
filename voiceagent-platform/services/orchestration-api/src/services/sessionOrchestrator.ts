/**
 * Coordinates call session lifecycle across telephony-gateway,
 * voice-pipeline, and agent-core. orchestration-api does not touch audio
 * or dialogue itself; it resolves tenant configuration and keeps a
 * durable record of session state for monitoring and the admin dashboard.
 */

export interface TenantConfig {
  tenantId: string;
  displayName: string;
  voiceId: string;
  language: string;
  allowedTools: string[];
  complianceMode: "standard" | "banking";
  /**
   * SIP trunks this tenant is allowed to receive calls on. telephony-gateway
   * resolves a tenant id from a dialplan/channel variable at the SIP layer
   * (see sip_handler.py's _resolve_tenant), which is carrier/PBX-controlled
   * input, not something orchestration-api itself signed. Trusting that
   * tenant id without cross-checking it against the trunk the call actually
   * arrived on would let a dialplan misconfiguration (or a carrier-side
   * bug) route a call into the wrong tenant's context — the one thing the
   * banking multi-tenancy guarantee cannot tolerate. This list is the
   * cross-check.
   */
  allowedSipTrunks: string[];
}

export interface CallSession {
  channelId: string;
  tenantId: string;
  sipTrunk: string;
  startedAt: string;
  endedAt: string | null;
  status: "active" | "completed" | "failed";
}

export class TenantTrunkMismatchError extends Error {
  constructor(tenantId: string, sipTrunk: string) {
    super(`tenant "${tenantId}" is not configured for SIP trunk "${sipTrunk}"`);
    this.name = "TenantTrunkMismatchError";
  }
}

export class SessionOrchestrator {
  private sessions = new Map<string, CallSession>();

  constructor(private readonly resolveTenantConfig: (tenantId: string) => Promise<TenantConfig>) {}

  /**
   * Starts a session for a call telephony-gateway has already resolved a
   * tenant id and SIP trunk for. The trunk is re-validated here against
   * that tenant's configuration rather than trusted as-is — see the
   * `allowedSipTrunks` doc comment on TenantConfig for why.
   */
  async startSession(channelId: string, tenantId: string, sipTrunk: string): Promise<CallSession> {
    const config = await this.resolveTenantConfig(tenantId);
    if (!config.allowedSipTrunks.includes(sipTrunk)) {
      throw new TenantTrunkMismatchError(tenantId, sipTrunk);
    }
    const session: CallSession = {
      channelId,
      tenantId: config.tenantId,
      sipTrunk,
      startedAt: new Date().toISOString(),
      endedAt: null,
      status: "active",
    };
    this.sessions.set(channelId, session);
    return session;
  }

  endSession(channelId: string, status: "completed" | "failed"): CallSession | undefined {
    const session = this.sessions.get(channelId);
    if (!session) return undefined;
    session.endedAt = new Date().toISOString();
    session.status = status;
    return session;
  }

  getSession(channelId: string): CallSession | undefined {
    return this.sessions.get(channelId);
  }
}
