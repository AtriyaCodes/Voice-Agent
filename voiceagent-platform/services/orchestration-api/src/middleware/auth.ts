import { NextFunction, Request, Response } from "express";
import jwt from "jsonwebtoken";

export interface TenantScopedRequest extends Request {
  tenantId?: string;
  sipTrunk?: string;
}

/**
 * Reads and validates JWT_SIGNING_SECRET once at module load, rather than
 * per request. A missing secret must crash the process on startup, not
 * fall back to an empty string that makes every token forgeable — the
 * tenant boundary for the whole platform rests on this check.
 */
export function loadJwtSigningSecret(env: NodeJS.ProcessEnv = process.env): string {
  const secret = env.JWT_SIGNING_SECRET;
  if (!secret || secret.trim().length === 0) {
    throw new Error(
      "JWT_SIGNING_SECRET is not set. Refusing to start with an empty/missing " +
        "signing secret: that would make every tenant token forgeable.",
    );
  }
  return secret;
}

interface TenantTokenPayload {
  tenantId: string;
  sipTrunk?: string;
}

/**
 * Resolves the calling tenant from a signed JWT and attaches it to the
 * request. Every downstream route reads tenantId from here rather than
 * trusting anything client supplied, which is what makes the multi-tenant
 * data segregation guarantee enforceable at the API boundary.
 *
 * The algorithm allowlist is not optional: jwt.verify() without an
 * `algorithms` option will accept whatever `alg` the token header claims,
 * which is the classic algorithm-confusion hole (e.g. an RS256-signed
 * token's public key gets misused as an HS256 secret). VoiceAgent only issues
 * HS256 tokens, so that is the only algorithm this ever accepts.
 */
export function requireTenant(secret: string) {
  return (req: TenantScopedRequest, res: Response, next: NextFunction): void => {
    const authHeader = req.headers.authorization;
    if (!authHeader?.startsWith("Bearer ")) {
      res.status(401).json({ error: "missing bearer token" });
      return;
    }

    const token = authHeader.slice("Bearer ".length);
    try {
      const payload = jwt.verify(token, secret, { algorithms: ["HS256"] }) as TenantTokenPayload;
      req.tenantId = payload.tenantId;
      req.sipTrunk = payload.sipTrunk;
      next();
    } catch {
      res.status(401).json({ error: "invalid token" });
    }
  };
}
