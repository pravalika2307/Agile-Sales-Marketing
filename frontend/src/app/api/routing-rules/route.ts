import { NextResponse } from "next/server";
import { extractAuthToken, getBackendUrl } from "@/lib/backend-auth";

export async function GET(request: Request) {
  try {
    const backendUrl = getBackendUrl();
    const token = extractAuthToken(request) || "";

    const response = await fetch(`${backendUrl}/api/v1/routing-rules`, {
      method: "GET",
      headers: {
        Authorization: `Bearer ${token}`,
        "Content-Type": "application/json",
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
  } catch (error) {
    console.error("Failed to fetch routing rules:", error);
    return NextResponse.json(
      { error: "Internal server error" },
      { status: 500 }
    );
  }
}

export async function POST(request: Request) {
  try {
    const backendUrl = getBackendUrl();
    const token = extractAuthToken(request) || "";
    const body = await request.json();

    const response = await fetch(`${backendUrl}/api/v1/routing-rules`, {
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
  } catch (error) {
    console.error("Failed to create routing rule:", error);
    return NextResponse.json(
      { error: "Internal server error" },
      { status: 500 }
    );
  }
}
