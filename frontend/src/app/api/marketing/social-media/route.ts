import { NextResponse } from "next/server";
import prisma from "@/lib/prisma";

export const dynamic = "force-dynamic";

export interface SocialMediaPostAnalytics {
  id: string;
  impressions: number;
  reach: number;
  likes: number;
  comments: number;
  shares: number;
  saves: number;
  totalEngagement: number;
  engagementRate: number;
  profileVisits: number;
  linkClicks: number;
  lastUpdated: string | Date;
}

export interface SocialMediaPostData {
  id: string;
  platform: "INSTAGRAM" | "FACEBOOK";
  topic: string;
  caption: string;
  format: string;
  contentPillar: string;
  permalink: string | null;
  scheduledDate: string | Date | null;
  status: string;
  externalPostId: string | null;
  analytics: SocialMediaPostAnalytics | null;
}

export async function GET() {
  try {
    // Fetch all posts from PostgreSQL where platform is INSTAGRAM or FACEBOOK
    const posts = await prisma.post.findMany({
      where: {
        platform: {
          in: ["INSTAGRAM", "FACEBOOK"],
        },
      },
      include: {
        analytics: true,
      },
      orderBy: [
        { scheduledDate: "desc" },
        { createdAt: "desc" },
      ],
    });

    const instagramPosts: SocialMediaPostData[] = [];
    const facebookPosts: SocialMediaPostData[] = [];

    for (const post of posts) {
      const formattedPost: SocialMediaPostData = {
        id: post.id,
        platform: post.platform as "INSTAGRAM" | "FACEBOOK",
        topic: post.topic,
        caption: post.caption,
        format: post.format,
        contentPillar: post.contentPillar,
        permalink: post.permalink,
        scheduledDate: post.scheduledDate,
        status: post.status,
        externalPostId: post.externalPostId,
        analytics: post.analytics
          ? {
              id: post.analytics.id,
              impressions: post.analytics.impressions,
              reach: post.analytics.reach,
              likes: post.analytics.likes,
              comments: post.analytics.comments,
              shares: post.analytics.shares,
              saves: post.analytics.saves,
              totalEngagement: post.analytics.totalEngagement,
              engagementRate: Number(post.analytics.engagementRate.toFixed(2)),
              profileVisits: post.analytics.profileVisits,
              linkClicks: post.analytics.linkClicks,
              lastUpdated: post.analytics.lastUpdated,
            }
          : null,
      };

      if (post.platform === "INSTAGRAM") {
        instagramPosts.push(formattedPost);
      } else if (post.platform === "FACEBOOK") {
        facebookPosts.push(formattedPost);
      }
    }

    // --- INSTAGRAM METRICS AGGREGATION ---
    let igTotalReach = 0;
    let igTotalLikes = 0;
    let igTotalComments = 0;
    let igTotalShares = 0;
    let igTotalSaves = 0;
    let igTotalEngagement = 0;
    let igSumEr = 0;
    let igErCount = 0;

    for (const p of instagramPosts) {
      if (p.analytics) {
        igTotalReach += p.analytics.reach;
        igTotalLikes += p.analytics.likes;
        igTotalComments += p.analytics.comments;
        igTotalShares += p.analytics.shares;
        igTotalSaves += p.analytics.saves;
        igTotalEngagement += p.analytics.totalEngagement;
        if (p.analytics.engagementRate > 0) {
          igSumEr += p.analytics.engagementRate;
          igErCount++;
        }
      }
    }

    const igAvgEr = igErCount > 0 ? Number((igSumEr / igErCount).toFixed(2)) : 0;

    // Identify Instagram top post (highest engagement rate)
    const igTopPost = [...instagramPosts].sort((a, b) => {
      const erA = a.analytics?.engagementRate ?? 0;
      const erB = b.analytics?.engagementRate ?? 0;
      if (erB !== erA) return erB - erA;
      return (b.analytics?.totalEngagement ?? 0) - (a.analytics?.totalEngagement ?? 0);
    })[0] || null;

    // --- FACEBOOK METRICS AGGREGATION ---
    let fbTotalEngagement = 0;
    let fbTotalReactions = 0;
    let fbTotalComments = 0;
    let fbTotalShares = 0;
    let fbTotalReach = 0;
    let fbSumEr = 0;
    let fbErCount = 0;

    for (const p of facebookPosts) {
      if (p.analytics) {
        fbTotalEngagement += p.analytics.totalEngagement;
        fbTotalReactions += p.analytics.likes; // Reactions mapped to likes in schema
        fbTotalComments += p.analytics.comments;
        fbTotalShares += p.analytics.shares;
        fbTotalReach += p.analytics.reach;
        if (p.analytics.engagementRate > 0) {
          fbSumEr += p.analytics.engagementRate;
          fbErCount++;
        }
      }
    }

    // If explicit ER values are absent on Facebook, calculate engagement rate per published post
    const fbAvgEngagementPerPost =
      facebookPosts.length > 0
        ? Number((fbTotalEngagement / facebookPosts.length).toFixed(2))
        : 0;
    const fbAvgEr =
      fbErCount > 0
        ? Number((fbSumEr / fbErCount).toFixed(2))
        : Number(((fbTotalEngagement / (fbTotalReach > 0 ? fbTotalReach : 500)) * 100).toFixed(2)) ||
          fbAvgEngagementPerPost;

    // Identify Facebook top post (highest total engagement / reactions)
    const fbTopPost = [...facebookPosts].sort((a, b) => {
      const engA = a.analytics?.totalEngagement ?? 0;
      const engB = b.analytics?.totalEngagement ?? 0;
      if (engB !== engA) return engB - engA;
      return (b.analytics?.likes ?? 0) - (a.analytics?.likes ?? 0);
    })[0] || null;

    return NextResponse.json({
      success: true,
      timestamp: new Date().toISOString(),
      data: {
        instagram: {
          kpis: {
            totalReach: igTotalReach,
            avgEngagementRate: igAvgEr,
            totalSaves: igTotalSaves,
            totalLikes: igTotalLikes,
            totalComments: igTotalComments,
            totalShares: igTotalShares,
            totalEngagement: igTotalEngagement,
            postCount: instagramPosts.length,
          },
          topPost: igTopPost,
          posts: instagramPosts,
        },
        facebook: {
          kpis: {
            totalEngagement: fbTotalEngagement,
            avgEngagementRate: fbAvgEr,
            totalReactions: fbTotalReactions,
            totalComments: fbTotalComments,
            totalShares: fbTotalShares,
            totalReach: fbTotalReach,
            avgEngagementPerPost: fbAvgEngagementPerPost,
            postCount: facebookPosts.length,
          },
          topPost: fbTopPost,
          posts: facebookPosts,
        },
      },
    });
  } catch (error: any) {
    console.error("Error fetching social media analytics:", error);
    return NextResponse.json(
      {
        success: false,
        error: "Failed to fetch social media analytics",
        details: error?.message || "Internal server error",
      },
      { status: 500 }
    );
  }
}
