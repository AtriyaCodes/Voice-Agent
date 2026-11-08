import {
  SessionOrchestrator,
  TenantConfig,
  TenantTrunkMismatchError,
} from "../src/services/sessionOrchestrator";

describe("SessionOrchestrator", () => {
  const fakeConfig: TenantConfig = {
    tenantId: "acme",
    displayName: "Acme Bank",
    voiceId: "voice-1",
    language: "en-IN",
    allowedTools: [],
    complianceMode: "standard",
    allowedSipTrunks: ["contosoip"],
  };

  it("starts and ends a session for a trunk the tenant is configured for", async () => {
    const orchestrator = new SessionOrchestrator(async () => fakeConfig);

    const session = await orchestrator.startSession("chan-1", "acme", "contosoip");
    expect(session.status).toBe("active");
    expect(session.sipTrunk).toBe("contosoip");

    const ended = orchestrator.endSession("chan-1", "completed");
    expect(ended?.status).toBe("completed");
    expect(ended?.endedAt).not.toBeNull();
  });

  it("rejects a call whose SIP trunk does not belong to the resolved tenant", async () => {
    const orchestrator = new SessionOrchestrator(async () => fakeConfig);

    await expect(orchestrator.startSession("chan-2", "acme", "some-other-trunk")).rejects.toThrow(
      TenantTrunkMismatchError,
    );
    expect(orchestrator.getSession("chan-2")).toBeUndefined();
  });
});
