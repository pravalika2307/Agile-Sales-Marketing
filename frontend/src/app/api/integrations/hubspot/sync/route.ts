import { NextResponse } from "next/server";
import crypto from "crypto";

function generateBackendToken(): string {
  const secret = process.env.BACKEND_SECRET_KEY || "09d25e094faa6ca2556c818166b7a9563b93f7099f6f0f4caa6cf63b88e8d3e7";
  const header = { alg: "HS256", typ: "JWT" };
  const now = Math.floor(Date.now() / 1000);
  const payload = {
    sub: "2c073c24-4ae1-4d58-8103-e2ae300d49e3",
    org_id: "0d85dc9f-1520-4bcb-8af4-8aad025255cb",
    role: "owner",
    type: "access",
    iat: now,
    exp: now + 3600,
  };

  const b64 = (s: string) =>
    Buffer.from(s)
      .toString("base64")
      .replace(/=/g, "")
      .replace(/\+/g, "-")
      .replace(/\//g, "_");

  const encHeader = b64(JSON.stringify(header));
  const encPayload = b64(JSON.stringify(payload));
  const sig = crypto
    .createHmac("sha256", secret)
    .update(`${encHeader}.${encPayload}`)
    .digest("base64")
    .replace(/=/g, "")
    .replace(/\+/g, "-")
    .replace(/\//g, "_");

  return `${encHeader}.${encPayload}.${sig}`;
}

export async function POST() {
  try {
    const backendUrl = process.env.BACKEND_URL || "http://127.0.0.1:8000";
    const token = generateBackendToken();

    const response = await fetch(`${backendUrl}/api/v1/integrations/hubspot/sync`, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${token}`,
        "Content-Type": "application/json",
      },
      cache: "no-store",
      signal: AbortSignal.timeout(60000),
    });

    if (!response.ok) {
      const errData = await response.json().catch(() => ({}));
      return NextResponse.json(
        { error: errData.detail || errData.message || `Backend returned ${response.status}` },
        { status: response.status }
      );
    }

    const data = await response.json();
    return NextResponse.json(data);
  } catch (error: any) {
    console.error("HubSpot sync proxy error:", error);
    const msg = error.name === "TimeoutError"
      ? "Synchronization backend request timed out after 60s"
      : error.message || "Failed to trigger synchronization on backend";
    return NextResponse.json(
      { error: msg },
      { status: 504 }
    );
  }
}
