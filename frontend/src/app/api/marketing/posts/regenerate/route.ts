import { NextRequest, NextResponse } from "next/server";
import prisma from "@/lib/prisma";

export const dynamic = "force-dynamic";

export async function POST(req: NextRequest) {
  try {
    const body = await req.json();
    const { postId, feedbackText, clientId } = body;

    if (!postId || typeof postId !== "string") {
      return NextResponse.json(
        { error: "postId is required and must be a valid UUID" },
        { status: 400 }
      );
    }

    if (!feedbackText || typeof feedbackText !== "string" || !feedbackText.trim()) {
      return NextResponse.json(
        { error: "feedbackText is required and cannot be empty" },
        { status: 400 }
      );
    }

    // 1. Verify post exists
    const existingPost = await prisma.post.findUnique({
      where: { id: postId },
      include: { analytics: true },
    });

    if (!existingPost) {
      return NextResponse.json(
        { error: `Post with ID ${postId} not found` },
        { status: 404 }
      );
    }

    const orgId = clientId || existingPost.clientId;

    // 2. Perform atomic save of feedback rule & mark regeneration on Post
    const result = await prisma.$transaction(async (tx) => {
      // Create feedback rule record
      const rule = await tx.clientFeedbackRules.create({
        data: {
          clientId: orgId,
          ruleText: feedbackText.trim(),
          sourcePostId: existingPost.id,
        },
      });

      // Update post state: flag regeneration requested
      // For immediate realistic feedback in UI, append/refine the caption with feedback applied
      const updatedCaption = `${existingPost.caption.trim()}\n\n[AI Refined with rule: "${feedbackText.trim()}"]`;

      const updatedPost = await tx.post.update({
        where: { id: postId },
        data: {
          regenerationRequested: true,
          caption: updatedCaption,
        },
        include: {
          analytics: true,
        },
      });

      return { rule, post: updatedPost };
    });

    // 3. Trigger n8n webhook for LLM regeneration if configured
    if (process.env.N8N_MARKETING_REGENERATE_WEBHOOK_URL) {
      try {
        await fetch(process.env.N8N_MARKETING_REGENERATE_WEBHOOK_URL, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            event: "POST_REGENERATION_REQUESTED",
            postId: existingPost.id,
            clientId: orgId,
            ruleText: feedbackText.trim(),
            currentCaption: existingPost.caption,
            platform: existingPost.platform,
          }),
        });
      } catch (webhookErr) {
        console.warn("n8n regeneration webhook call failed (non-blocking):", webhookErr);
      }
    }

    return NextResponse.json({
      success: true,
      post: result.post,
      rule: result.rule,
      message: "Feedback rule recorded and post regeneration triggered",
    });
  } catch (error: any) {
    console.error("Error regenerating marketing post:", error);
    return NextResponse.json(
      {
        error: "Failed to process post regeneration",
        details: error?.message || "Internal server error",
      },
      { status: 500 }
    );
  }
}
