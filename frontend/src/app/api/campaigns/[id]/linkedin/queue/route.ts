import { NextResponse } from "next/server";
import { extractAuthToken, getBackendUrl } from "@/lib/backend-auth";

interface RouteParams {
  params: Promise<{ id: string }>;
}

export async function GET(request: Request, context: RouteParams) {
  try {
    const { id } = await context.params;
    const backendUrl = getBackendUrl();
    const token = extractAuthToken(request) || "";

    const response = await fetch(`${backendUrl}/api/v1/integrations/linkedin/campaigns/${id}/queue`, {
      method: "GET",
      headers: {
        Authorization: `Bearer ${token}`,
        "Content-Type": "application/json",
      },
      cache: "no-store",
    });

    if (!response.ok) {
      const errData = await response.json().catch(() => ({}));
      return NextResponse.json(
        { error: errData.detail || errData.error || `Backend returned ${response.status}` },
        { status: response.status }
      );
    }

    const data = await response.json();
    return NextResponse.json(data);
  } catch (error: unknown) {
    console.error("API GET /api/campaigns/[id]/linkedin/queue error:", error);
    return NextResponse.json(
      { error: "Internal server error fetching LinkedIn assisted campaign queue." },
      { status: 500 }
    );
  }
}
