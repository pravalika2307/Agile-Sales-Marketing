import { NextResponse } from "next/server";
import { extractAuthToken, getBackendUrl } from "@/lib/backend-auth";

export async function GET(request: Request) {
  try {
    const backendUrl = getBackendUrl();
    const token = extractAuthToken(request) || "";
    const { searchParams } = new URL(request.url);
    const queryString = searchParams.toString() ? `?${searchParams.toString()}` : "";

    const response = await fetch(`${backendUrl}/api/v1/outreach${queryString}`, {
      method: "GET",
      headers: {
        Authorization: `Bearer ${token}`,
        "Content-Type": "application/json",
      },
      cache: "no-store",
    });

    if (!response.ok) {
      return NextResponse.json(
        { error: `Backend returned ${response.status}` },
        { status: response.status }
      );
    }

    const data = await response.json();
    const totalCount =
      response.headers.get("x-total-count") ||
      response.headers.get("X-Total-Count") ||
      String(Array.isArray(data) ? data.length : 0);

    return NextResponse.json(data, {
      headers: {
        "X-Total-Count": totalCount,
      },
    });
  } catch (error: unknown) {
    console.error("API GET /api/outreach error:", error);
    return NextResponse.json(
      { error: "Internal server error connecting to backend." },
      { status: 500 }
    );
  }
}
