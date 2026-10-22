import { NextResponse } from "next/server";
import prisma from "@/lib/prisma";
import { PostStatus, Platform } from "@prisma/client";

export const dynamic = "force-dynamic";

export interface KanbanResponseCard {
  id: string;
  title: string;
  summary: string;
  platforms: ("linkedin" | "instagram" | "x" | "facebook")[];
  status: PostStatus;
  columnId: "backlog" | "in_progress" | "awaiting_approval" | "scheduled" | "posted";
  statusBadge: {
    label: string;
    variant: "new" | "priority" | "review" | "scheduled" | "default";
  };
  thumbnailUrl: string;
  scheduledDate: string;
  authorName: string;
  authorInitials: string;
  aiCost: number | null;
  contentPillar: string;
  permalink: string | null;
  analytics: {
    impressions: number;
    reach: number;
    likes: number;
    comments: number;
    shares: number;
    totalEngagement: number;
    engagementRate: number;
    linkClicks: number;
  } | null;
}

function getThumbnailForPost(topic: string, pillar: string, platform: Platform): string {
  const t = topic.toLowerCase();
  const p = pillar.toLowerCase();

  if (t.includes("interview") || t.includes("video")) {
    return "https://images.unsplash.com/photo-1534528741775-53994a69daeb?w=160&auto=format&fit=crop&q=80";
  }
  if (t.includes("healthcare") || t.includes("patient") || p.includes("healthcare")) {
    return "https://images.unsplash.com/photo-1576091160550-2173dba999ef?w=160&auto=format&fit=crop&q=80";
  }
  if (t.includes("nudge") || t.includes("sms") || t.includes("voice") || t.includes("remind")) {
    return "https://images.unsplash.com/photo-1557804506-669a67965ba0?w=160&auto=format&fit=crop&q=80";
  }
  if (t.includes("dispute") || t.includes("cfo") || t.includes("dso") || t.includes("financial")) {
    return "https://images.unsplash.com/photo-1551836022-d5d88e9218df?w=160&auto=format&fit=crop&q=80";
  }
  if (platform === Platform.INSTAGRAM) {
    return "https://images.unsplash.com/photo-1611162617474-5b21e879e113?w=160&auto=format&fit=crop&q=80";
  }
  return "https://images.unsplash.com/photo-1460925895917-afdab827c52f?w=160&auto=format&fit=crop&q=80";
}

function mapStatusToBadge(status: PostStatus): {
  label: string;
  variant: "new" | "priority" | "review" | "scheduled" | "default";
} {
  switch (status) {
    case PostStatus.BACKLOG:
      return { label: "Backlog", variant: "new" };
    case PostStatus.IN_PROGRESS:
      return { label: "In Progress", variant: "default" };
    case PostStatus.AWAITING_APPROVAL:
      return { label: "Awaiting Sign-off", variant: "review" };
    case PostStatus.SCHEDULED:
      return { label: "Scheduled", variant: "scheduled" };
    case PostStatus.POSTED:
      return { label: "Published", variant: "priority" };
  }
}

function mapStatusToColumn(
  status: PostStatus
): "backlog" | "in_progress" | "awaiting_approval" | "scheduled" | "posted" {
  switch (status) {
    case PostStatus.BACKLOG:
      return "backlog";
    case PostStatus.IN_PROGRESS:
      return "in_progress";
    case PostStatus.AWAITING_APPROVAL:
      return "awaiting_approval";
    case PostStatus.SCHEDULED:
      return "scheduled";
    case PostStatus.POSTED:
      return "posted";
  }
}

export async function GET() {
  try {
    const posts = await prisma.post.findMany({
      include: {
        analytics: true,
      },
      orderBy: [
        { scheduledDate: "asc" },
        { createdAt: "desc" },
      ],
    });

    const cards: KanbanResponseCard[] = posts.map((p, idx) => {
      const platformKey = p.platform.toLowerCase() as "linkedin" | "instagram" | "x" | "facebook";
      const platforms = [platformKey];
      if (p.platform === Platform.FACEBOOK) platforms.push("instagram");

      const columnId = mapStatusToColumn(p.status);
      const statusBadge = mapStatusToBadge(p.status);
      const thumbnailUrl = getThumbnailForPost(p.topic, p.contentPillar, p.platform);

      let formattedDate = "TBD";
      if (p.scheduledDate) {
        const d = new Date(p.scheduledDate);
        formattedDate = d.toLocaleDateString("en-US", {
          month: "short",
          day: "numeric",
          year: "numeric",
        });
      }

      // Rotating team authors for rich visual distinction
      const authors = [
        { name: "Pravalika Palle", initials: "PP" },
        { name: "Lakshay Narula", initials: "LN" },
        { name: "Marcus Chen", initials: "MC" },
      ];
      const author = authors[idx % authors.length];

      return {
        id: p.id,
        title: p.topic,
        summary: p.caption ? p.caption.slice(0, 140) : p.contentPillar,
        platforms,
        status: p.status,
        columnId,
        statusBadge,
        thumbnailUrl,
        scheduledDate: formattedDate,
        authorName: author.name,
        authorInitials: author.initials,
        aiCost: p.aiCost,
        contentPillar: p.contentPillar,
        permalink: p.permalink,
        analytics: p.analytics
          ? {
              impressions: p.analytics.impressions,
              reach: p.analytics.reach,
              likes: p.analytics.likes,
              comments: p.analytics.comments,
              shares: p.analytics.shares,
              totalEngagement: p.analytics.totalEngagement,
              engagementRate: p.analytics.engagementRate,
              linkClicks: p.analytics.linkClicks,
            }
          : null,
      };
    });

    // Group cards by column
    const grouped = {
      backlog: cards.filter((c) => c.columnId === "backlog"),
      in_progress: cards.filter((c) => c.columnId === "in_progress"),
      awaiting_approval: cards.filter((c) => c.columnId === "awaiting_approval"),
      scheduled: cards.filter((c) => c.columnId === "scheduled"),
      posted: cards.filter((c) => c.columnId === "posted"),
    };

    return NextResponse.json({
      total: cards.length,
      grouped,
      cards,
    });
  } catch (error: unknown) {
    console.error("API GET /api/marketing/kanban error:", error);
    return NextResponse.json(
      { error: "Internal server error fetching Kanban posts." },
      { status: 500 }
    );
  }
}

export async function PATCH(request: Request) {
  try {
    const body = await request.json();
    const { postId, columnId, status } = body;

    if (!postId) {
      return NextResponse.json({ error: "Missing postId parameter" }, { status: 400 });
    }

    let targetStatus: PostStatus = PostStatus.BACKLOG;
    if (status) {
      targetStatus = status as PostStatus;
    } else if (columnId) {
      switch (columnId) {
        case "backlog":
          targetStatus = PostStatus.BACKLOG;
          break;
        case "in_progress":
          targetStatus = PostStatus.IN_PROGRESS;
          break;
        case "awaiting_approval":
          targetStatus = PostStatus.AWAITING_APPROVAL;
          break;
        case "scheduled":
          targetStatus = PostStatus.SCHEDULED;
          break;
        case "posted":
          targetStatus = PostStatus.POSTED;
          break;
      }
    }

    const updatedPost = await prisma.post.update({
      where: { id: postId },
      data: { status: targetStatus },
    });

    return NextResponse.json({
      success: true,
      post: updatedPost,
    });
  } catch (error: unknown) {
    console.error("API PATCH /api/marketing/kanban error:", error);
    return NextResponse.json(
      { error: "Internal server error updating post status." },
      { status: 500 }
    );
  }
}
