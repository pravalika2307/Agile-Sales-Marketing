import { NextRequest, NextResponse } from "next/server";
import { extractAuthToken, getBackendUrl, handleBackendProxyError } from "@/lib/backend-auth";

export async function GET(request: NextRequest) {
  try {
    const backendUrl = getBackendUrl();
    const token = extractAuthToken(request);
    const { searchParams } = new URL(request.url);
    const queryString = searchParams.toString();
    const targetUrl = `${backendUrl}/api/v1/voice/agents${queryString ? `?${queryString}` : ""}`;

    const res = await fetch(targetUrl, {
      method: "GET",
      headers: {
        "Content-Type": "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      cache: "no-store",
    });

    const data = await res.json().catch(() => ({}));
    return NextResponse.json(data, { status: res.status });
  } catch (error) {
    return handleBackendProxyError(error, "GET /api/v1/voice/agents");
  }
}
