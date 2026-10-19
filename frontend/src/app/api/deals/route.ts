import { NextResponse } from "next/server";
import { extractAuthToken, getBackendUrl } from "@/lib/backend-auth";

export async function GET(request: Request) {
  try {
    const backendUrl = getBackendUrl();
    const token = extractAuthToken(request) || "";
    const { searchParams } = new URL(request.url);
    const queryString = searchParams.toString() ? `?${searchParams.toString()}` : "";

    const response = await fetch(`${backendUrl}/api/v1/deals${queryString}`, {
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
    console.error("API GET /api/deals error:", error);
    return NextResponse.json(
      { error: "Internal server error connecting to deals API." },
      { status: 500 }
    );
  }
}

export async function POST(request: Request) {
  try {
    const backendUrl = getBackendUrl();
    const token = extractAuthToken(request) || "";
    const body = await request.json();

    const response = await fetch(`${backendUrl}/api/v1/deals`, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${token}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify(body),
    });

    if (!response.ok) {
      const errorText = await response.text();
      return NextResponse.json(
        { error: errorText || `Backend returned ${response.status}` },
        { status: response.status }
      );
    }

    const data = await response.json();
    return NextResponse.json(data, { status: 201 });
  } catch (error: unknown) {
    console.error("API POST /api/deals error:", error);
    return NextResponse.json(
      { error: "Internal server error creating deal." },
      { status: 500 }
    );
  }
}
