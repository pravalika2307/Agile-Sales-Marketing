import { NextResponse } from "next/server";
import { generateBackendToken, getBackendUrl } from "@/lib/backend-auth";

export async function GET(
  request: Request,
  { params }: { params: Promise<{ id: string }> }
) {
  try {
    const { id } = await params;
    const backendUrl = getBackendUrl();
    const token = generateBackendToken();

    const response = await fetch(`${backendUrl}/api/v1/deals/${id}`, {
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
    console.error("API GET /api/deals/[id] error:", error);
    return NextResponse.json(
      { error: "Internal server error fetching deal." },
      { status: 500 }
    );
  }
}

export async function PATCH(
  request: Request,
  { params }: { params: Promise<{ id: string }> }
) {
  try {
    const { id } = await params;
    const backendUrl = getBackendUrl();
    const token = generateBackendToken();
    const body = await request.json();

    const response = await fetch(`${backendUrl}/api/v1/deals/${id}`, {
      method: "PATCH",
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
    return NextResponse.json(data);
  } catch (error: unknown) {
    console.error("API PATCH /api/deals/[id] error:", error);
    return NextResponse.json(
      { error: "Internal server error updating deal." },
      { status: 500 }
    );
  }
}

export async function DELETE(
  request: Request,
  { params }: { params: Promise<{ id: string }> }
) {
  try {
    const { id } = await params;
    const backendUrl = getBackendUrl();
    const token = generateBackendToken();

    const response = await fetch(`${backendUrl}/api/v1/deals/${id}`, {
      method: "DELETE",
      headers: {
        Authorization: `Bearer ${token}`,
      },
    });

    if (!response.ok && response.status !== 204) {
      const errorText = await response.text();
      return NextResponse.json(
        { error: errorText || `Backend returned ${response.status}` },
        { status: response.status }
      );
    }

    return new NextResponse(null, { status: 204 });
  } catch (error: unknown) {
    console.error("API DELETE /api/deals/[id] error:", error);
    return NextResponse.json(
      { error: "Internal server error deleting deal." },
      { status: 500 }
    );
  }
}
