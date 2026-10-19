import { NextResponse } from "next/server";
import { extractAuthToken, getBackendUrl } from "@/lib/backend-auth";

export async function GET(request: Request) {
  try {
    const { searchParams } = new URL(request.url);
    const backendUrl = getBackendUrl();
    const token = extractAuthToken(request) || "";

    const response = await fetch(`${backendUrl}/api/v1/templates?${searchParams.toString()}`, {
      headers: {
        Authorization: `Bearer ${token}`,
      },
      cache: "no-store",
    });

    if (!response.ok) {
      const errText = await response.text();
      return NextResponse.json(
        { error: `Backend returned ${response.status}: ${errText}` },
        { status: response.status }
      );
    }

    const data = await response.json();
    return NextResponse.json(data);
  } catch (error: unknown) {
    console.error("API GET /api/templates error:", error);
    return NextResponse.json(
      { error: "Internal server error fetching templates." },
      { status: 500 }
    );
  }
}

export async function POST(request: Request) {
  try {
    const backendUrl = getBackendUrl();
    const token = extractAuthToken(request) || "";
    const body = await request.json();

    const response = await fetch(`${backendUrl}/api/v1/templates`, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${token}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify(body),
    });

    if (!response.ok) {
      const errText = await response.text();
      return NextResponse.json(
        { error: `Backend returned ${response.status}: ${errText}` },
        { status: response.status }
      );
    }

    const data = await response.json();
    return NextResponse.json(data, { status: 201 });
  } catch (error: unknown) {
    console.error("API POST /api/templates error:", error);
    return NextResponse.json(
      { error: "Internal server error saving template." },
      { status: 500 }
    );
  }
}
