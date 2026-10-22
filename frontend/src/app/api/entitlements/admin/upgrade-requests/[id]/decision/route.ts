import { NextResponse } from "next/server";
import {
  extractAuthToken,
  getBackendUrl,
  handleBackendProxyError,
} from "@/lib/backend-auth";

export async function POST(
  request: Request,
  { params }: { params: Promise<{ id: string }> }
) {
  try {
    const { id } = await params;
    const backendUrl = getBackendUrl();
    const token = extractAuthToken(request) || "";
    const body = await request.json();

    const response = await fetch(
      `${backendUrl}/api/v1/entitlements/admin/upgrade-requests/${id}/decision`,
      {
        method: "POST",
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify(body),
      }
    );

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
    return handleBackendProxyError(error, "entitlements/admin/upgrade-requests/[id]/decision");
  }
}
