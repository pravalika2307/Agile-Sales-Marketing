import { NextRequest, NextResponse } from "next/server";
import { getBackendUrl, handleBackendProxyError } from "@/lib/backend-auth";

export async function POST(request: NextRequest) {
  try {
    const backendUrl = getBackendUrl();
    const refreshToken = request.cookies.get("refresh_token")?.value;

    if (!refreshToken) {
      return NextResponse.json(
        { detail: "Refresh token was not provided." },
        { status: 401 }
      );
    }

    const response = await fetch(`${backendUrl}/api/v1/auth/refresh`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ refresh_token: refreshToken }),
      cache: "no-store",
    });

    const data = await response.json().catch(() => ({}));

    if (!response.ok) {
      // Clear cookies if refresh token is invalid or expired
      const isProduction = process.env.NODE_ENV === "production";
      const res = NextResponse.json(data, { status: response.status });
      res.cookies.set("auth_token", "", {
        maxAge: 0,
        path: "/",
        secure: isProduction,
        httpOnly: true,
        sameSite: "lax",
      });
      res.cookies.set("refresh_token", "", {
        maxAge: 0,
        path: "/",
        secure: isProduction,
        httpOnly: true,
        sameSite: "lax",
      });
      res.cookies.set("agile_user", "", {
        maxAge: 0,
        path: "/",
        secure: isProduction,
        httpOnly: false,
        sameSite: "lax",
      });
      return res;
    }

    const { access_token, refresh_token: new_refresh_token, token_type } = data;
    const isProduction = process.env.NODE_ENV === "production";

    const res = NextResponse.json({
      success: true,
      tokens: { access_token, refresh_token: new_refresh_token, token_type },
    });

    // 1. Set updated HttpOnly auth_token cookie (30 minutes)
    res.cookies.set("auth_token", access_token, {
      httpOnly: true,
      secure: isProduction,
      sameSite: "lax",
      path: "/",
      maxAge: 1800, // 30 minutes
    });

    // 2. Set updated HttpOnly refresh_token cookie (14 days)
    res.cookies.set("refresh_token", new_refresh_token, {
      httpOnly: true,
      secure: isProduction,
      sameSite: "lax",
      path: "/",
      maxAge: 14 * 24 * 3600, // 14 days
    });

    return res;
  } catch (error: unknown) {
    return handleBackendProxyError(error, "auth/refresh");
  }
}
