import { NextRequest, NextResponse } from "next/server";
import { extractAuthToken, getBackendUrl, handleBackendProxyError } from "@/lib/backend-auth";

export async function POST(request: NextRequest) {
  try {
    const backendUrl = getBackendUrl();
    const token = extractAuthToken(request);
    const body = await request.json().catch(() => ({}));

    const res = await fetch(`${backendUrl}/api/v1/sms/validate-phone`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify(body),
      cache: "no-store",
    });

    const data = await res.json().catch(() => ({}));
    return NextResponse.json(data, { status: res.status });
  } catch (error) {
    return handleBackendProxyError(error, "POST /api/v1/sms/validate-phone");
  }
}
