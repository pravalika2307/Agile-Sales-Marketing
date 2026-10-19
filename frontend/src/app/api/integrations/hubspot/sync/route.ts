import { NextResponse } from "next/server";
import { extractAuthToken, getBackendUrl } from "@/lib/backend-auth";

export async function POST(request: Request) {
  try {
    const backendUrl = process.env.BACKEND_URL || "http://127.0.0.1:8000";
    const token = extractAuthToken(request) || "";

    const response = await fetch(`${backendUrl}/api/v1/integrations/hubspot/sync`, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${token}`,
        "Content-Type": "application/json",
      },
      cache: "no-store",
      signal: AbortSignal.timeout(60000),
    });

    if (!response.ok) {
      const errData = await response.json().catch(() => ({}));
      return NextResponse.json(
        { error: errData.detail || errData.message || `Backend returned ${response.status}` },
        { status: response.status }
      );
    }

    const data = await response.json();
    return NextResponse.json(data);
  } catch (error: any) {
    console.error("HubSpot sync proxy error:", error);
    const msg = error.name === "TimeoutError"
      ? "Synchronization backend request timed out after 60s"
      : error.message || "Failed to trigger synchronization on backend";
    return NextResponse.json(
      { error: msg },
      { status: 504 }
    );
  }
}
