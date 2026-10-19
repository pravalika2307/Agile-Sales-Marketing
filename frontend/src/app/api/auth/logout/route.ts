import { NextRequest, NextResponse } from "next/server";
import { getBackendUrl } from "@/lib/backend-auth";

export async function POST(request: NextRequest) {
  const backendUrl = getBackendUrl();
  const authToken = request.cookies.get("auth_token")?.value;

  // Best-effort call to backend logout endpoint
  try {
    await fetch(`${backendUrl}/api/v1/auth/logout`, {
      method: "POST",
      headers: {
        ...(authToken ? { Authorization: `Bearer ${authToken}` } : {}),
      },
      cache: "no-store",
    });
  } catch {
    // Continue clearing client-side cookies even if backend is temporarily unreachable
  }

  const res = NextResponse.json({
    success: true,
    message: "Logged out successfully.",
  });

  const isProduction = process.env.NODE_ENV === "production";

  // Expire all session cookies immediately
  res.cookies.set("auth_token", "", {
    httpOnly: true,
    secure: isProduction,
    sameSite: "lax",
    path: "/",
    maxAge: 0,
  });

  res.cookies.set("refresh_token", "", {
    httpOnly: true,
    secure: isProduction,
    sameSite: "lax",
    path: "/",
    maxAge: 0,
  });

  res.cookies.set("agile_user", "", {
    httpOnly: false,
    secure: isProduction,
    sameSite: "lax",
    path: "/",
    maxAge: 0,
  });

  return res;
}
