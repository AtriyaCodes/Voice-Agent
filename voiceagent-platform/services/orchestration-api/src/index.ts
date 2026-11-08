import express from "express";
import pino from "pino";

import { loadJwtSigningSecret, requireTenant } from "./middleware/auth";
import { sessionsRouter } from "./routes/sessions";
import { tenantsRouter } from "./routes/tenants";
import { SessionOrchestrator, TenantConfig } from "./services/sessionOrchestrator";

const logger = pino();

// Fails process startup (not the first request) if JWT_SIGNING_SECRET is
// missing — see loadJwtSigningSecret's doc comment.
const jwtSigningSecret = loadJwtSigningSecret();

const app = express();
app.use(express.json());

async function resolveTenantConfig(tenantId: string): Promise<TenantConfig> {
  // Placeholder: wire to the tenant configuration store (Postgres).
  return {
    tenantId,
    displayName: tenantId,
    voiceId: "default",
    language: "en-IN",
    allowedTools: [],
    complianceMode: "standard",
    allowedSipTrunks: [process.env.DEFAULT_SIP_TRUNK ?? "default"],
  };
}

const orchestrator = new SessionOrchestrator(resolveTenantConfig);

app.get("/healthz", (_req, res) => res.json({ status: "ok" }));
app.use("/api", requireTenant(jwtSigningSecret), sessionsRouter(orchestrator));
app.use("/api", requireTenant(jwtSigningSecret), tenantsRouter());

const port = Number(process.env.ORCHESTRATION_API_PORT ?? 8080);
app.listen(port, () => {
  logger.info({ port }, "orchestration-api listening");
});
