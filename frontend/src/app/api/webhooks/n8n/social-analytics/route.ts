import { NextRequest, NextResponse } from "next/server";
import prisma from "@/lib/prisma";
import { Platform, PostFormat, PostStatus } from "@prisma/client";

export const dynamic = "force-dynamic";

export async function POST(req: NextRequest) {
  try {
    // 1. Webhook Authentication
    const authHeader = req.headers.get("Authorization");
    const expectedSecret = process.env.N8N_WEBHOOK_SECRET || "agile_n8n_secret_2026";

    const token = authHeader?.startsWith("Bearer ")
      ? authHeader.slice(7).trim()
      : null;

    if (!token || token !== expectedSecret) {
      return NextResponse.json(
        {
          error: "Unauthorized",
          message: "Invalid or missing Bearer token in Authorization header",
        },
        { status: 401 }
      );
    }

    // 2. Parse Incoming Payload
    const body = await req.json().catch(() => null);
    if (!body) {
      return NextResponse.json(
        { error: "Bad Request", message: "Invalid JSON payload" },
        { status: 400 }
      );
    }

    // Support direct array or wrapped data/posts properties from n8n nodes
    let rawPosts: any[] = [];
    if (Array.isArray(body)) {
      rawPosts = body;
    } else if (body && Array.isArray(body.data)) {
      rawPosts = body.data;
    } else if (body && Array.isArray(body.posts)) {
      rawPosts = body.posts;
    } else if (body && Array.isArray(body.body)) {
      rawPosts = body.body;
    } else if (body && typeof body === "object") {
      rawPosts = [body];
    }

    if (rawPosts.length === 0) {
      return NextResponse.json({
        success: true,
        count: 0,
        message: "No post objects found in incoming payload",
      });
    }

    // 3. Resolve Organization / Client Record
    let organization = await prisma.organizations.findFirst();
    if (!organization) {
      organization = await prisma.organizations.create({
        data: {
          id: crypto.randomUUID(),
          name: "Agile Receivables",
          slug: "agile-receivables",
          created_at: new Date(),
          updated_at: new Date(),
        },
      });
    }

    // 4. Atomic Parsing & Upsert Logic (Prisma Transaction)
    const results = await prisma.$transaction(async (tx) => {
      const processed: any[] = [];

      for (const item of rawPosts) {
        if (!item || typeof item !== "object") continue;

        // A. Extract Permalink
        const permalink = String(
          item.Permalink || item.permalink || item.url || item.link || ""
        ).trim() || null;

        // B. Identify Platform based on Permalink / explicit field
        let platform: Platform = Platform.INSTAGRAM;
        const permalinkLower = String(permalink || "").toLowerCase();
        const rawPlatform = String(item.Platform || item.platform || "").toUpperCase();

        if (permalinkLower.includes("facebook.com") || rawPlatform === "FACEBOOK") {
          platform = Platform.FACEBOOK;
        } else if (permalinkLower.includes("instagram.com") || rawPlatform === "INSTAGRAM") {
          platform = Platform.INSTAGRAM;
        } else if (permalinkLower.includes("linkedin.com") || rawPlatform === "LINKEDIN") {
          platform = Platform.LINKEDIN;
        } else if (
          permalinkLower.includes("x.com") ||
          permalinkLower.includes("twitter.com") ||
          rawPlatform === "X"
        ) {
          platform = Platform.X;
        }

        // C. Map Post ID to externalPostId
        const externalPostId = String(
          item["Post ID"] ??
            item.externalPostId ??
            item.postId ??
            item.id ??
            item.external_post_id ??
            ""
        ).trim();

        if (!externalPostId && !permalink) {
          continue; // Skip items without any unique identifier
        }

        // D. Map Date & Time to combined scheduledDate (DateTime object)
        let scheduledDate: Date | null = null;
        const rawDate =
          item.Date ||
          item.date ||
          item.scheduledDate ||
          item.scheduled_date ||
          item.created_time ||
          item["Created Time"];
        const rawTime = item.Time || item.time;

        if (rawDate) {
          if (rawTime && typeof rawDate === "string" && typeof rawTime === "string") {
            const combined = `${rawDate.trim()}T${rawTime.trim()}`;
            const parsed = new Date(combined);
            scheduledDate = isNaN(parsed.getTime()) ? new Date(rawDate) : parsed;
          } else {
            const parsed = new Date(rawDate);
            scheduledDate = isNaN(parsed.getTime()) ? null : parsed;
          }
        }

        // E. Caption, Topic & Pillar
        const caption = String(
          item.Caption ?? item.caption ?? item.text ?? item.message ?? ""
        ).trim();
        const fallbackTopic = caption
          ? caption.length > 80
            ? `${caption.slice(0, 80)}...`
            : caption
          : "Social Media Post";
        const topic = String(item.Topic ?? item.topic ?? fallbackTopic).trim();
        const contentPillar = String(
          item["Content Pillar"] ?? item.contentPillar ?? item.content_pillar ?? "Social Media"
        ).trim();

        // F. Format: Media Type (if IG) or Post Type (if FB)
        const rawFormat = String(
          item["Media Type"] ?? item["Post Type"] ?? item.format ?? item.media_type ?? ""
        ).toUpperCase();
        let format: PostFormat = PostFormat.SINGLE_IMAGE;
        if (rawFormat.includes("VIDEO") || rawFormat.includes("REEL")) {
          format = PostFormat.VIDEO;
        } else if (rawFormat.includes("CAROUSEL") || rawFormat.includes("ALBUM")) {
          format = PostFormat.CAROUSEL;
        }

        // G. Metrics Parsing
        // likes: Likes (IG) or Reactions (FB)
        const rawLikes = item.Likes ?? item.Reactions ?? item.likes ?? item.reactions ?? 0;
        const likes =
          typeof rawLikes === "string"
            ? parseInt(rawLikes.replace(/[^0-9]/g, ""), 10) || 0
            : Number(rawLikes) || 0;

        const rawComments = item.Comments ?? item.comments ?? 0;
        const comments =
          typeof rawComments === "string"
            ? parseInt(rawComments.replace(/[^0-9]/g, ""), 10) || 0
            : Number(rawComments) || 0;

        const rawShares = item.Shares ?? item.shares ?? 0;
        const shares =
          typeof rawShares === "string"
            ? parseInt(rawShares.replace(/[^0-9]/g, ""), 10) || 0
            : Number(rawShares) || 0;

        // saves: Saves (IG only, default to 0 for FB)
        const rawSaves =
          platform === Platform.INSTAGRAM ? item.Saves ?? item.saves ?? 0 : 0;
        const saves =
          typeof rawSaves === "string"
            ? parseInt(rawSaves.replace(/[^0-9]/g, ""), 10) || 0
            : Number(rawSaves) || 0;

        // reach: Reach (IG only, default to 0 for FB)
        const rawReach =
          platform === Platform.INSTAGRAM ? item.Reach ?? item.reach ?? 0 : 0;
        const reach =
          typeof rawReach === "string"
            ? parseInt(rawReach.replace(/[^0-9]/g, ""), 10) || 0
            : Number(rawReach) || 0;

        // totalEngagement: Total Engagement
        const rawTotalEngagement =
          item["Total Engagement"] ?? item.totalEngagement ?? item.total_engagement;
        let totalEngagement = 0;
        if (rawTotalEngagement !== undefined && rawTotalEngagement !== null) {
          totalEngagement =
            typeof rawTotalEngagement === "string"
              ? parseInt(rawTotalEngagement.replace(/[^0-9]/g, ""), 10) || 0
              : Number(rawTotalEngagement) || 0;
        } else {
          totalEngagement = likes + comments + shares + saves;
        }

        // engagementRate: Engagement Rate
        const rawEr = item["Engagement Rate"] ?? item.engagementRate ?? item.engagement_rate;
        let engagementRate = 0.0;
        if (rawEr !== undefined && rawEr !== null) {
          if (typeof rawEr === "string") {
            engagementRate = parseFloat(rawEr.replace(/%/g, "").trim()) || 0.0;
          } else {
            engagementRate = Number(rawEr) || 0.0;
          }
        } else if (reach > 0) {
          engagementRate = Number(((totalEngagement / reach) * 100).toFixed(2));
        }

        // lastUpdated: Last Updated (Convert ISO string to DateTime)
        const rawUpdated = item["Last Updated"] ?? item.lastUpdated ?? item.last_updated;
        let lastUpdated = new Date();
        if (rawUpdated) {
          const parsedUpdated = new Date(rawUpdated);
          if (!isNaN(parsedUpdated.getTime())) {
            lastUpdated = parsedUpdated;
          }
        }

        // H. Upsert Post Table (prevent duplicates based on externalPostId or permalink)
        let postRecord: any = null;
        if (externalPostId) {
          postRecord = await tx.post.findFirst({
            where: { externalPostId },
          });
        }
        if (!postRecord && permalink) {
          postRecord = await tx.post.findFirst({
            where: { permalink },
          });
        }

        if (postRecord) {
          postRecord = await tx.post.update({
            where: { id: postRecord.id },
            data: {
              platform,
              caption: caption || postRecord.caption,
              permalink: permalink || postRecord.permalink,
              format,
              topic: topic || postRecord.topic,
              contentPillar: contentPillar || postRecord.contentPillar,
              scheduledDate: scheduledDate || postRecord.scheduledDate,
              status: PostStatus.POSTED,
            },
          });
        } else {
          postRecord = await tx.post.create({
            data: {
              clientId: organization.id,
              platform,
              externalPostId: externalPostId || null,
              caption,
              topic,
              contentPillar,
              format,
              permalink,
              scheduledDate,
              status: PostStatus.POSTED,
            },
          });
        }

        // I. Upsert PostAnalytics Table
        const analyticsRecord = await tx.postAnalytics.upsert({
          where: { postId: postRecord.id },
          update: {
            likes,
            comments,
            shares,
            saves,
            reach,
            totalEngagement,
            engagementRate,
            lastUpdated,
          },
          create: {
            postId: postRecord.id,
            likes,
            comments,
            shares,
            saves,
            reach,
            totalEngagement,
            engagementRate,
            lastUpdated,
          },
        });

        processed.push({
          id: postRecord.id,
          externalPostId: postRecord.externalPostId,
          platform: postRecord.platform,
          totalEngagement: analyticsRecord.totalEngagement,
          engagementRate: analyticsRecord.engagementRate,
          lastUpdated: analyticsRecord.lastUpdated,
        });
      }

      return processed;
    });

    return NextResponse.json({
      success: true,
      received: rawPosts.length,
      processed: results.length,
      data: results,
      message: `Successfully processed and upserted ${results.length} social post analytics records from n8n`,
    });
  } catch (error: any) {
    console.error("Error in n8n social analytics webhook receiver:", error);
    return NextResponse.json(
      {
        error: "Internal Server Error",
        details: error?.message || "Failed to process webhook payload",
      },
      { status: 500 }
    );
  }
}
