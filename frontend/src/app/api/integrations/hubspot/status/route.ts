import { NextResponse } from "next/server";
import { extractAuthToken, getBackendUrl } from "@/lib/backend-auth";

export async function GET(request: Request) {
  try {
    const backendUrl = process.env.BACKEND_URL || "http://127.0.0.1:8000";
    const token = extractAuthToken(request) || "";

    const response = await fetch(`${backendUrl}/api/v1/integrations/hubspot/status`, {
      method: "GET",
      headers: {
        Authorization: `Bearer ${token}`,
        "Content-Type": "application/json",
      },
      cache: "no-store",
      signal: AbortSignal.timeout(20000),
    });

    if (!response.ok) {
      const errData = await response.json().catch(() => ({}));
      return NextResponse.json(
        { error: errData.detail || errData.message || `Backend returned HTTP ${response.status}` },
        { status: response.status }
      );
    }

    const data = await response.json();
    return NextResponse.json(data);
  } catch (error: any) {
    console.error("HubSpot status proxy error:", error);
    const msg = error.name === "TimeoutError" 
      ? "Backend connection timed out after 12s" 
      : error.message || "Failed to connect to backend service";
    return NextResponse.json(
      { error: msg },
      { status: 504 }
    );
  }
}
