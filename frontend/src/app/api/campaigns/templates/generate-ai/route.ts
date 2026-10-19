import { NextResponse } from "next/server";
import { extractAuthToken, getBackendUrl } from "@/lib/backend-auth";

export async function POST(request: Request) {
  try {
    const backendUrl = getBackendUrl();
    const token = extractAuthToken(request) || "";
    const body = await request.json();

    const response = await fetch(`${backendUrl}/api/v1/campaigns/templates/generate-ai`, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${token}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify(body),
    });

    if (!response.ok) {
      const errText = await response.text();
      let errorDetail = `Backend error ${response.status}`;
      try {
        const parsed = JSON.parse(errText);
        errorDetail = parsed.detail || parsed.error || errorDetail;
      } catch {
        errorDetail = errText || errorDetail;
      }
      return NextResponse.json(
        { error: errorDetail },
        { status: response.status }
      );
    }

    const data = await response.json();
    return NextResponse.json(data);
  } catch (error: unknown) {
    console.error("API POST /api/campaigns/templates/generate-ai error:", error);
    return NextResponse.json(
      { error: "Internal server error generating AI email content." },
      { status: 500 }
    );
  }
}
