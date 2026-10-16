import { NextResponse } from "next/server";
import { generateBackendToken, getBackendUrl } from "@/lib/backend-auth";

export async function POST() {
  try {
    const backendUrl = getBackendUrl();
    const token = generateBackendToken();

    const response = await fetch(`${backendUrl}/api/v1/lists/sync-sources`, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${token}`,
        "Content-Type": "application/json",
      },
    });

    const data = await response.json();
    return NextResponse.json(data, { status: response.status });
  } catch (error: unknown) {
    console.error("API POST /api/lists/sync-sources error:", error);
    return NextResponse.json({ error: "Failed to sync source lists" }, { status: 500 });
  }
}
