import { NextRequest, NextResponse } from "next/server";

// Public auth pages that unauthenticated users can access
const publicPaths = [
  "/login",
  "/register",
  "/forgot-password",
];

// Public API endpoints that don't require an active session
const publicApiPrefixes = [
  "/api/auth/login",
  "/api/auth/logout",
  "/api/auth/register",
  "/api/auth/refresh",
];

/**
 * Validate JWT structure and unexpired state for Next.js Edge routing decisions.
 *
 * IMPORTANT SECURITY NOTE:
 * Edge middleware decoding is strictly an unauthenticated structural and expiration
 * pre-filter to prevent redirect loops and serving authenticated page shells for dead sessions.
 * It is NOT proof of identity; authoritative cryptographic signature verification and
 * tenant isolation are exclusively enforced on the backend.
 */
function isTokenStructureValidAndUnexpired(token: string | undefined): boolean {
  if (!token || typeof token !== "string" || !token.trim()) {
    return false;
  }

  const parts = token.trim().split(".");
  if (parts.length !== 3) {
    return false; // Malformed JWT (not 3 period-separated segments)
  }

  try {
    // Base64URL decode the payload (second segment)
    let base64 = parts[1].replace(/-/g, "+").replace(/_/g, "/");
    while (base64.length % 4 !== 0) {
      base64 += "=";
    }
    const jsonString = atob(base64);
    const payload = JSON.parse(jsonString);

    if (!payload || typeof payload !== "object") {
      return false;
    }

    // Must have subject and numeric exp claims
    if (!payload.sub || typeof payload.exp !== "number") {
      return false;
    }

    // Check expiration timestamp (0s tolerance to prevent serving stale shells)
    const nowInSeconds = Math.floor(Date.now() / 1000);
    if (payload.exp <= nowInSeconds) {
      return false; // Expired session
    }

    return true;
  } catch {
    return false;
  }
}

export function middleware(request: NextRequest) {
  const { pathname, search } = request.nextUrl;

  // 1. Bypass static files, internal Next.js assets, and images
  if (
    pathname.startsWith("/_next") ||
    pathname.startsWith("/auth/") ||
    pathname.includes(".") // favicon.ico, logo.svg, images, etc.
  ) {
    return NextResponse.next();
  }

  // 2. Validate token structure and expiration (never rely solely on cookie presence)
  const authToken = request.cookies.get("auth_token")?.value;
  const isAuthenticated = isTokenStructureValidAndUnexpired(authToken);
  const hasStaleCookie = Boolean(authToken && !isAuthenticated);

  const isPublicPath = publicPaths.some(
    (path) => pathname === path || pathname.startsWith(`${path}/`)
  );

  const isPublicApi = publicApiPrefixes.some(
    (prefix) => pathname === prefix || pathname.startsWith(`${prefix}/`)
  );

  // 3. Case A: Unauthenticated user accessing protected API route -> 401 Unauthorized
  if (!isAuthenticated && pathname.startsWith("/api") && !isPublicApi) {
    const response = NextResponse.json(
      {
        error: "Unauthorized",
        message: hasStaleCookie
          ? "Session has expired or is invalid. Please sign in again."
          : "Authentication required to access this resource.",
      },
      { status: 401 }
    );
    if (hasStaleCookie) {
      response.cookies.delete("auth_token");
      response.cookies.delete("refresh_token");
      response.cookies.delete("agile_user");
    }
    return response;
  }

  // 4. Case B: Unauthenticated user accessing protected application page -> Redirect to /login
  if (!isAuthenticated && !isPublicPath && !pathname.startsWith("/api")) {
    const redirectUrl = new URL("/login", request.url);
    const destination = `${pathname}${search}`;
    if (destination && destination !== "/") {
      redirectUrl.searchParams.set("redirect", destination);
    }
    if (hasStaleCookie) {
      redirectUrl.searchParams.set("reason", "expired");
    }
    const response = NextResponse.redirect(redirectUrl);
    if (hasStaleCookie) {
      response.cookies.delete("auth_token");
      response.cookies.delete("refresh_token");
      response.cookies.delete("agile_user");
    }
    return response;
  }

  // 5. Case C: Authenticated user accessing public path (e.g. /login) -> Redirect to dashboard
  if (isAuthenticated && isPublicPath) {
    const target = request.nextUrl.searchParams.get("redirect") || "/";
    const redirectUrl = new URL(target.startsWith("/") ? target : "/", request.url);
    return NextResponse.redirect(redirectUrl);
  }

  // 6. Case D: Stale/expired cookie accessing public path (e.g. /login) -> Clear stale cookies
  if (hasStaleCookie && isPublicPath) {
    const response = NextResponse.next();
    response.cookies.delete("auth_token");
    response.cookies.delete("refresh_token");
    response.cookies.delete("agile_user");
    return response;
  }

  // 7. Case E: Allowed request -> Add strict cache-control to prevent caching sensitive data
  const response = NextResponse.next();
  response.headers.set(
    "Cache-Control",
    "no-store, no-cache, must-revalidate, proxy-revalidate"
  );
  response.headers.set("Pragma", "no-cache");
  response.headers.set("Expires", "0");

  return response;
}

export const config = {
  matcher: [
    /*
     * Match all request paths except for:
     * - _next/static (static files)
     * - _next/image (image optimization files)
     * - favicon.ico, logo.svg, etc.
     */
    "/((?!_next/static|_next/image|favicon.ico|.*\\.(?:svg|png|jpg|jpeg|gif|webp)$).*)",
  ],
};
