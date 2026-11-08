import { Router } from "express";
import { TenantScopedRequest } from "../middleware/auth";
import { SessionOrchestrator } from "../services/sessionOrchestrator";

export function sessionsRouter(orchestrator: SessionOrchestrator): Router {
  const router = Router();

  router.get("/sessions/:channelId", (req: TenantScopedRequest, res) => {
    const session = orchestrator.getSession(req.params.channelId);
    if (!session) {
      res.status(404).json({ error: "session not found" });
      return;
    }
    if (session.tenantId !== req.tenantId) {
      res.status(403).json({ error: "session does not belong to this tenant" });
      return;
    }
    res.json(session);
  });

  return router;
}
