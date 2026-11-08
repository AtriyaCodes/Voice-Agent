import jwt from "jsonwebtoken";
import { NextFunction, Response } from "express";

import { loadJwtSigningSecret, requireTenant, TenantScopedRequest } from "../src/middleware/auth";

function fakeRes(): Response {
  const res: Partial<Response> = {
    status: jest.fn().mockReturnThis(),
    json: jest.fn().mockReturnThis(),
  };
  return res as Response;
}

describe("loadJwtSigningSecret", () => {
  it("throws when JWT_SIGNING_SECRET is unset, instead of defaulting to an empty secret", () => {
    expect(() => loadJwtSigningSecret({})).toThrow(/JWT_SIGNING_SECRET/);
  });

  it("throws when JWT_SIGNING_SECRET is set to an empty/whitespace string", () => {
    expect(() => loadJwtSigningSecret({ JWT_SIGNING_SECRET: "   " })).toThrow(/JWT_SIGNING_SECRET/);
  });

  it("returns the secret when set", () => {
    expect(loadJwtSigningSecret({ JWT_SIGNING_SECRET: "s3cret" })).toBe("s3cret");
  });
});

describe("requireTenant", () => {
  const secret = "s3cret";

  it("accepts a validly signed HS256 token and attaches tenantId", () => {
    const token = jwt.sign({ tenantId: "acme" }, secret, { algorithm: "HS256" });
    const req = { headers: { authorization: `Bearer ${token}` } } as TenantScopedRequest;
    const res = fakeRes();
    const next = jest.fn() as NextFunction;

    requireTenant(secret)(req, res, next);

    expect(next).toHaveBeenCalled();
    expect(req.tenantId).toBe("acme");
  });

  it("rejects a token signed with a different algorithm than the allowlisted one", () => {
    // none-algorithm / mismatched-algorithm tokens are the classic
    // algorithm-confusion attack this allowlist exists to block.
    const forgedHeader = Buffer.from(JSON.stringify({ alg: "none", typ: "JWT" })).toString(
      "base64url",
    );
    const forgedPayload = Buffer.from(JSON.stringify({ tenantId: "acme" })).toString("base64url");
    const forgedToken = `${forgedHeader}.${forgedPayload}.`;

    const req = { headers: { authorization: `Bearer ${forgedToken}` } } as TenantScopedRequest;
    const res = fakeRes();
    const next = jest.fn() as NextFunction;

    requireTenant(secret)(req, res, next);

    expect(next).not.toHaveBeenCalled();
    expect(res.status).toHaveBeenCalledWith(401);
  });

  it("rejects a missing bearer token", () => {
    const req = { headers: {} } as TenantScopedRequest;
    const res = fakeRes();
    const next = jest.fn() as NextFunction;

    requireTenant(secret)(req, res, next);

    expect(next).not.toHaveBeenCalled();
    expect(res.status).toHaveBeenCalledWith(401);
  });
});
