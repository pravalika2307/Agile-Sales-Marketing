import { NextResponse } from "next/server";
import { generateBackendToken, getBackendUrl } from "@/lib/backend-auth";

interface RouteContext {
  params: Promise<{ id: string; listId: string }>;
}

export async function DELETE(request: Request, context: RouteContext) {
  try {
    const { id, listId } = await context.params;
    const backendUrl = getBackendUrl();
    const token = generateBackendToken();

    const response = await fetch(`${backendUrl}/api/v1/campaigns/${id}/lists/${listId}`, {
      method: "DELETE",
      headers: {
        Authorization: `Bearer ${token}`,
      },
    });

    if (response.status === 204) {
      return new NextResponse(null, { status: 204 });
    }
    const data = await response.json().catch(() => ({}));
    return NextResponse.json(data, { status: response.status });
  } catch (error: unknown) {
    console.error("API DELETE /api/campaigns/[id]/lists/[listId] error:", error);
    return NextResponse.json({ error: "Failed to detach list from campaign" }, { status: 500 });
  }
}
