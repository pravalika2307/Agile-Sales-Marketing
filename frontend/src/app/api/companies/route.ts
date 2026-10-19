import { NextResponse } from "next/server";
import {
  extractAuthToken,
  getBackendUrl,
  handleBackendProxyError,
} from "@/lib/backend-auth";

export async function GET(request: Request) {
  try {
    const backendUrl = getBackendUrl();
    const token = extractAuthToken(request) || "";
    const { searchParams } = new URL(request.url);
    const queryString = searchParams.toString() ? `?${searchParams.toString()}` : "";

    const response = await fetch(`${backendUrl}/api/v1/companies${queryString}`, {
      method: "GET",
      headers: {
        Authorization: `Bearer ${token}`,
        "Content-Type": "application/json",
      },
      cache: "no-store",
    });

    if (!response.ok) {
      let payload: unknown;
      try {
        payload = await response.json();
      } catch {
        const text = await response.text().catch(() => "");
        payload = { error: text || `Backend returned status ${response.status}` };
      }
      return NextResponse.json(payload, { status: response.status });
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
    return handleBackendProxyError(error, "companies");
  }
}

export async function POST(request: Request) {
  try {
    const backendUrl = getBackendUrl();
    const token = extractAuthToken(request) || "";
    const body = await request.json();

    const response = await fetch(`${backendUrl}/api/v1/companies`, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${token}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify(body),
    });

    if (!response.ok) {
      let payload: unknown;
      try {
        payload = await response.json();
      } catch {
        const text = await response.text().catch(() => "");
        payload = { error: text || `Backend returned status ${response.status}` };
      }
      return NextResponse.json(payload, { status: response.status });
    }

    const data = await response.json();
    return NextResponse.json(data, { status: 201 });
  } catch (error: unknown) {
    return handleBackendProxyError(error, "companies");
  }
}
