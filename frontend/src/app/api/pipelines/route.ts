import { NextResponse } from "next/server";
import { generateBackendToken, getBackendUrl } from "@/lib/backend-auth";

export async function GET() {
  try {
    const backendUrl = getBackendUrl();
    const token = generateBackendToken();

    const response = await fetch(`${backendUrl}/api/v1/pipelines`, {
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
    console.error("API GET /api/pipelines error:", error);
    return NextResponse.json(
      { error: "Internal server error connecting to pipelines API." },
      { status: 500 }
    );
  }
}

export async function POST(request: Request) {
  try {
    const backendUrl = getBackendUrl();
    const token = generateBackendToken();
    const body = await request.json();

    const response = await fetch(`${backendUrl}/api/v1/pipelines`, {
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
    console.error("API POST /api/pipelines error:", error);
    return NextResponse.json(
      { error: "Internal server error creating pipeline." },
      { status: 500 }
    );
  }
}
