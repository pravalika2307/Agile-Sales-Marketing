import { NextRequest, NextResponse } from "next/server";
import { getBackendUrl, handleBackendProxyError } from "@/lib/backend-auth";

export async function GET(request: NextRequest) {
  try {
    const backendUrl = getBackendUrl();
    const token =
      request.cookies.get("auth_token")?.value ||
      request.headers.get("authorization")?.replace(/^Bearer\s+/i, "");

    if (!token) {
      return NextResponse.json(
        { detail: "Authentication credentials were not provided." },
        { status: 401 }
      );
    }

    const response = await fetch(`${backendUrl}/api/v1/auth/me`, {
      method: "GET",
      headers: {
        Authorization: `Bearer ${token}`,
        "Content-Type": "application/json",
      },
      cache: "no-store",
    });

    const data = await response.json().catch(() => ({}));
    return NextResponse.json(data, { status: response.status });
  } catch (error: unknown) {
    return handleBackendProxyError(error, "auth/me");
  }
}
