import { NextResponse } from "next/server";
import { generateBackendToken, getBackendUrl } from "@/lib/backend-auth";

interface RouteContext {
  params: Promise<{ id: string; listId: string }>;
}

export async function POST(request: Request, context: RouteContext) {
  try {
    const { id, listId } = await context.params;
    const backendUrl = getBackendUrl();
    const token = generateBackendToken();

    const response = await fetch(`${backendUrl}/api/v1/campaigns/${id}/lists/${listId}/sync`, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${token}`,
      },
    });

    const data = await response.json();
    return NextResponse.json(data, { status: response.status });
  } catch (error: unknown) {
    console.error("API POST /api/campaigns/[id]/lists/[listId]/sync error:", error);
    return NextResponse.json({ error: "Failed to sync campaign list" }, { status: 500 });
  }
}
