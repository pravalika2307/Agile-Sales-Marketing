import { NextRequest, NextResponse } from "next/server";
import { getBackendUrl, handleBackendProxyError } from "@/lib/backend-auth";

export async function POST(request: NextRequest) {
  try {
    const backendUrl = getBackendUrl();
    const body = await request.json();

    const { email, password } = body;
    if (!email || !password) {
      return NextResponse.json(
        { detail: "Email and password are required." },
        { status: 400 }
      );
    }

    const response = await fetch(`${backendUrl}/api/v1/auth/login`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ email, password }),
      cache: "no-store",
    });

    const data = await response.json().catch(() => ({}));

    if (!response.ok) {
      return NextResponse.json(data, { status: response.status });
    }

    const { user, organization, tokens } = data;
    const isProduction = process.env.NODE_ENV === "production";

    const res = NextResponse.json({
      success: true,
      user,
      organization,
    });

    // 1. Set HttpOnly auth_token cookie (matches backend 30m access token expiry)
    res.cookies.set("auth_token", tokens.access_token, {
      httpOnly: true,
      secure: isProduction,
      sameSite: "lax",
      path: "/",
      maxAge: 1800, // 30 minutes
    });

    // 2. Set HttpOnly refresh_token cookie (matches backend 14 days refresh token expiry)
    res.cookies.set("refresh_token", tokens.refresh_token, {
      httpOnly: true,
      secure: isProduction,
      sameSite: "lax",
      path: "/",
      maxAge: 14 * 24 * 3600, // 14 days
    });

    // 3. Set readable agile_user cookie for UI profile presentation
    const userSummary = {
      id: user.id,
      email: user.email,
      name: user.full_name,
      role: user.role,
      access_level: user.access_level || "both",
      organization_id: organization?.id || user.organization_id,
      organization_name: organization?.name || "Agile Sales & Marketing",
    };

    res.cookies.set("agile_user", JSON.stringify(userSummary), {
      httpOnly: false,
      secure: isProduction,
      sameSite: "lax",
      path: "/",
      maxAge: 14 * 24 * 3600, // 14 days
    });

    return res;
  } catch (error: unknown) {
    return handleBackendProxyError(error, "auth/login");
  }
}
