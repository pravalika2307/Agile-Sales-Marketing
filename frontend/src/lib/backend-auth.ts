import crypto from "crypto";

export function generateBackendToken(): string {
  const secret =
    process.env.BACKEND_SECRET_KEY ||
    "09d25e094faa6ca2556c818166b7a9563b93f7099f6f0f4caa6cf63b88e8d3e7";
  const header = { alg: "HS256", typ: "JWT" };
  const now = Math.floor(Date.now() / 1000);
  const payload = {
    sub: "2c073c24-4ae1-4d58-8103-e2ae300d49e3",
    org_id: "0d85dc9f-1520-4bcb-8af4-8aad025255cb",
    role: "owner",
    type: "access",
    iat: now,
    exp: now + 3600,
  };

  const b64 = (s: string) =>
    Buffer.from(s)
      .toString("base64")
      .replace(/=/g, "")
      .replace(/\+/g, "-")
      .replace(/\//g, "_");

  const encHeader = b64(JSON.stringify(header));
  const encPayload = b64(JSON.stringify(payload));
  const sig = crypto
    .createHmac("sha256", secret)
    .update(`${encHeader}.${encPayload}`)
    .digest("base64")
    .replace(/=/g, "")
    .replace(/\+/g, "-")
    .replace(/\//g, "_");

  return `${encHeader}.${encPayload}.${sig}`;
}

export function getBackendUrl(): string {
  return process.env.BACKEND_URL || "http://127.0.0.1:8000";
}

export function isConnectionError(error: unknown): boolean {
  if (!error) return false;
  const err = error as Record<string, unknown>;
  if (
    err.code === "ECONNREFUSED" ||
    (err.cause as Record<string, unknown> | undefined)?.code === "ECONNREFUSED" ||
    (err.cause as Record<string, unknown> | undefined)?.code === "ENOTFOUND" ||
    (err.cause as Record<string, unknown> | undefined)?.code === "ECONNRESET"
  ) {
    return true;
  }
  const msg = typeof err.message === "string" ? err.message : "";
  return (
    msg.includes("fetch failed") ||
    msg.includes("ECONNREFUSED") ||
    msg.includes("connect ECONNREFUSED") ||
    msg.includes("ECONNRESET")
  );
}

export function handleBackendProxyError(error: unknown, resource: string) {
  const backendUrl = getBackendUrl();
  if (isConnectionError(error)) {
    console.error(
      `[backend-proxy] Connection error for ${resource}: backend service at ${backendUrl} is unreachable`
    );
    return Response.json(
      {
        error: `Backend service is unreachable at ${backendUrl}. Please ensure the backend server is running.`,
        code: "BACKEND_UNAVAILABLE",
      },
      { status: 503 }
    );
  }

  console.error(`[backend-proxy] Error proxying ${resource}:`, error);
  const message = error instanceof Error ? error.message : "Internal server error";
  return Response.json(
    {
      error: `Internal server error proxying ${resource}: ${message}`,
      code: "INTERNAL_SERVER_ERROR",
    },
    { status: 500 }
  );
}
