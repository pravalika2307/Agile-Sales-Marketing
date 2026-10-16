import { NextResponse } from "next/server";
import { generateBackendToken, getBackendUrl } from "@/lib/backend-auth";

interface RouteContext {
  params: Promise<{ id: string; memberId: string }>;
}

export async function DELETE(request: Request, context: RouteContext) {
  try {
    const { id, memberId } = await context.params;
    const backendUrl = getBackendUrl();
    const token = generateBackendToken();

    const response = await fetch(`${backendUrl}/api/v1/lists/${id}/members/${memberId}`, {
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
    console.error("API DELETE /api/lists/[id]/members/[memberId] error:", error);
    return NextResponse.json({ error: "Failed to remove member from list" }, { status: 500 });
  }
}
