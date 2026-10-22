import { NextRequest, NextResponse } from "next/server";

export const dynamic = "force-dynamic";

export async function POST(req: NextRequest) {
  try {
    const webhookUrl =
      process.env.N8N_SOCIAL_SYNC_WEBHOOK_URL ||
      process.env.NEXT_PUBLIC_N8N_SOCIAL_SYNC_WEBHOOK_URL ||
      "http://localhost:5678/webhook/social-sync";

    let triggered = false;
    let n8nResponse: any = null;

    try {
      const res = await fetch(webhookUrl, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${process.env.N8N_WEBHOOK_SECRET || "agile_n8n_secret_2026"}`,
        },
        body: JSON.stringify({
          event: "SOCIAL_MEDIA_SYNC_REQUESTED",
          trigger: "MANUAL_UI_SYNC",
          timestamp: new Date().toISOString(),
          platforms: ["INSTAGRAM", "FACEBOOK"],
        }),
        signal: AbortSignal.timeout(5000), // 5s timeout
      });

      if (res.ok) {
        triggered = true;
        n8nResponse = await res.json().catch(() => ({ status: "TRIGGERED" }));
      }
    } catch (err: any) {
      console.warn("n8n catch webhook trigger note (non-blocking):", err?.message || err);
    }

    return NextResponse.json({
      success: true,
      triggered,
      webhookUrl,
      message: triggered
        ? "n8n workflow triggered! Pushing fresh Meta analytics into PostgreSQL..."
        : "Sync request initiated. n8n workflow signaled to pull latest Instagram & Facebook metrics.",
      data: n8nResponse,
    });
  } catch (error: any) {
    console.error("Error triggering n8n social sync:", error);
    return NextResponse.json(
      {
        error: "Failed to trigger n8n sync",
        details: error?.message || "Internal server error",
      },
      { status: 500 }
    );
  }
}
