import { Router } from "express";
import { TenantScopedRequest } from "../middleware/auth";

/**
 * Tenant configuration CRUD, used by the admin dashboard. Reads and
 * writes go through here rather than services touching tenant config
 * storage directly, so there is one place that enforces who can change
 * what for a given tenant.
 */
export function tenantsRouter(): Router {
  const router = Router();

  router.get("/tenants/:tenantId", (req: TenantScopedRequest, res) => {
    if (req.params.tenantId !== req.tenantId) {
      res.status(403).json({ error: "cannot access another tenant's configuration" });
      return;
    }
    res.status(501).json({ error: "not implemented: wire to tenant config store" });
  });

  return router;
}
