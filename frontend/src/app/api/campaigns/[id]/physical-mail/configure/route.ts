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

    const response = await fetch(`${backendUrl}/api/v1/campaigns/${id}/physical-mail/configure`, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${token}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify(body),
    });

    if (!response.ok) {
      const errData = await response.json().catch(() => ({}));
      const detail = errData.detail;
      if (typeof detail === "object" && detail !== null) {
        return NextResponse.json(
          {
            error: detail.message || errData.error || `Backend returned ${response.status}`,
            poplar_campaign_id: detail.poplar_campaign_id,
            code: detail.code,
          },
          { status: response.status }
        );
      }
      return NextResponse.json(
        { error: detail || errData.error || `Backend returned ${response.status}` },
        { status: response.status }
      );
    }

    const data = await response.json();
    return NextResponse.json(data);
  } catch (error: unknown) {
    console.error("API POST /api/campaigns/[id]/physical-mail/configure error:", error);
    return NextResponse.json(
      { error: "Internal server error configuring physical mail campaign." },
      { status: 500 }
    );
  }
}
