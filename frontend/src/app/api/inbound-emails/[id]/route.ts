import { NextResponse } from "next/server";
import {
  extractAuthToken,
  getBackendUrl,
  handleBackendProxyError,
} from "@/lib/backend-auth";

export async function GET(
  request: Request,
  { params }: { params: Promise<{ id: string }> }
) {
  try {
    const { id } = await params;
    const backendUrl = getBackendUrl();
    const token = extractAuthToken(request) || "";

    const response = await fetch(`${backendUrl}/api/v1/inbound-emails/${id}`, {
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
    return NextResponse.json(data);
  } catch (error: unknown) {
    return handleBackendProxyError(error, "inbound-emails/[id]");
  }
}
