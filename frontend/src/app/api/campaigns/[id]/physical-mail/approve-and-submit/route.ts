import { NextResponse } from "next/server";
import { extractAuthToken, getBackendUrl } from "@/lib/backend-auth";

interface RouteParams {
  params: Promise<{ id: string }>;
}

export async function POST(request: Request, context: RouteParams) {
  try {
    const { id } = await context.params;
    const backendUrl = getBackendUrl();
    const token = extractAuthToken(request) || "";
    const body = await request.json().catch(() => ({}));

    const response = await fetch(`${backendUrl}/api/v1/campaigns/${id}/physical-mail/approve-and-submit`, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${token}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify(body),
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
    console.error("API POST /api/campaigns/[id]/physical-mail/approve-and-submit error:", error);
    return NextResponse.json(
      { error: "Internal server error submitting physical mail campaign." },
      { status: 500 }
    );
  }
}
