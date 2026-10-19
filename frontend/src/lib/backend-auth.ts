/**
 * Helper utilities for Next.js proxy route handlers communicating with FastAPI backend.
 * Extracts genuine authentication tokens from client requests (no mock or dev bypass paths).
 */

/**
 * Extract auth token from incoming request (Cookie: auth_token=<jwt> or Authorization: Bearer <jwt>).
 * Returns null if no genuine token is provided in cookies or headers.
 */
export function extractAuthToken(request?: Request): string | null {
  if (!request) return null;

  // 1. Check Cookie header
  const cookieHeader = request.headers.get("cookie");
  if (cookieHeader) {
    const match = cookieHeader.match(/(?:^|;\s*)auth_token=([^;]+)/);
    if (match && match[1]) {
      return decodeURIComponent(match[1]);
    }
  }

  // 2. Check Authorization header
  const authHeader = request.headers.get("authorization");
  if (authHeader && authHeader.toLowerCase().startsWith("bearer ")) {
    return authHeader.substring(7).trim();
  }

  return null;
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
