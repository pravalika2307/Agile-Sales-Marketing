import { NextResponse } from "next/server";
import { generateBackendToken, getBackendUrl } from "@/lib/backend-auth";

export async function GET(request: Request) {
  try {
    const backendUrl = getBackendUrl();
    const token = generateBackendToken();
    const { searchParams } = new URL(request.url);
    const queryString = searchParams.toString() ? `?${searchParams.toString()}` : "";

    const response = await fetch(`${backendUrl}/api/v1/analytics/activities${queryString}`, {
      method: "GET",
      headers: {
        Authorization: `Bearer ${token}`,
        "Content-Type": "application/json",
      },
      cache: "no-store",
    });

    if (!response.ok) {
      const errorText = await response.text();
      return NextResponse.json(
        { error: errorText || `Backend returned ${response.status}` },
        { status: response.status }
      );
    }

    const data = await response.json();
    return NextResponse.json(data);
  } catch (error: unknown) {
    console.error("API GET /api/analytics/activities error:", error);
    return NextResponse.json(
      { error: "Internal server error connecting to activities API." },
      { status: 500 }
    );
  }
}
