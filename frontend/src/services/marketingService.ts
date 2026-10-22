/**
 * Marketing API Client Service
 * Bridges frontend UI components with Prisma Next.js API endpoints
 */

export interface MarketingKpiCardItem {
  id: string;
  title: string;
  value: string;
  change: string;
  isPositive: boolean;
  subtext: string;
  sparklineData: number[];
  color: string;
  iconBg: string;
  iconColor: string;
}

export interface MarketingKpiResponse {
  targetMonth: string;
  target: any;
  metrics: {
    totalReach: number;
    avgEngagementRate: number;
    totalLinkClicks: number;
    actualDemoRequests: number;
    totalEngagement: number;
    totalImpressions: number;
  };
  cards: MarketingKpiCardItem[];
}

export interface KanbanCardData {
  id: string;
  title: string;
  summary: string;
  platforms: ("linkedin" | "instagram" | "x" | "facebook")[];
  status: "BACKLOG" | "IN_PROGRESS" | "AWAITING_APPROVAL" | "SCHEDULED" | "POSTED";
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

export interface KanbanBoardResponse {
  total: number;
  grouped: {
    backlog: KanbanCardData[];
    in_progress: KanbanCardData[];
    awaiting_approval: KanbanCardData[];
    scheduled: KanbanCardData[];
    posted: KanbanCardData[];
  };
  cards: KanbanCardData[];
}

export interface ChartPointData {
  date: string;
  displayDate: string;
  organicTraffic: number;
  paidConversions: number;
}

export interface ChartDataResponse {
  range: string;
  points: ChartPointData[];
  summary: {
    totalOrganic: number;
    totalConversions: number;
    conversionRate: string;
    yoyGrowth: string;
  };
}

export interface AIInsightData {
  id: string;
  type: "recommendation" | "performance" | "audience" | "optimization";
  badge: string;
  text: string;
  impactScore?: string;
  category: string;
  dateGenerated: string;
}

export interface AIInsightsResponse {
  success: boolean;
  insights: AIInsightData[];
  message?: string;
}

export async function fetchMarketingKpis(): Promise<MarketingKpiResponse> {
  const res = await fetch("/api/marketing/kpis", {
    method: "GET",
    headers: { "Content-Type": "application/json" },
    cache: "no-store",
  });
  if (!res.ok) {
    throw new Error(`Failed to fetch marketing KPIs: ${res.statusText}`);
  }
  return res.json();
}

export async function fetchMarketingKanban(): Promise<KanbanBoardResponse> {
  const res = await fetch("/api/marketing/kanban", {
    method: "GET",
    headers: { "Content-Type": "application/json" },
    cache: "no-store",
  });
  if (!res.ok) {
    throw new Error(`Failed to fetch marketing Kanban: ${res.statusText}`);
  }
  return res.json();
}

export async function updateKanbanPostStatus(
  postId: string,
  columnId: string
): Promise<{ success: boolean; post: any }> {
  const res = await fetch("/api/marketing/kanban", {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ postId, columnId }),
  });
  if (!res.ok) {
    throw new Error(`Failed to update post status: ${res.statusText}`);
  }
  return res.json();
}

export async function fetchMarketingChart(
  range: "7d" | "30d" | "90d" = "30d"
): Promise<ChartDataResponse> {
  const res = await fetch(`/api/marketing/chart?range=${range}`, {
    method: "GET",
    headers: { "Content-Type": "application/json" },
    cache: "no-store",
  });
  if (!res.ok) {
    throw new Error(`Failed to fetch marketing chart: ${res.statusText}`);
  }
  return res.json();
}

export async function fetchMarketingInsights(): Promise<AIInsightsResponse> {
  const res = await fetch("/api/marketing/insights", {
    method: "GET",
    headers: { "Content-Type": "application/json" },
    cache: "no-store",
  });
  if (!res.ok) {
    throw new Error(`Failed to fetch marketing AI insights: ${res.statusText}`);
  }
  return res.json();
}

export async function regenerateMarketingInsights(): Promise<AIInsightsResponse> {
  const res = await fetch("/api/marketing/insights", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
  });
  if (!res.ok) {
    throw new Error(`Failed to regenerate AI insights: ${res.statusText}`);
  }
  return res.json();
}

export async function createMarketingCampaign(
  formData: FormData
): Promise<{ success: boolean; campaign: any; message?: string }> {
  const res = await fetch("/api/marketing/campaigns/create", {
    method: "POST",
    body: formData,
  });
  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}));
    throw new Error(errorData.error || `Failed to create marketing campaign: ${res.statusText}`);
  }
  return res.json();
}

export async function regeneratePostWithFeedback(
  postId: string,
  feedbackText: string,
  clientId?: string
): Promise<{ success: boolean; post: any; rule?: any; message?: string }> {
  const res = await fetch("/api/marketing/posts/regenerate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ postId, feedbackText, clientId }),
  });
  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}));
    throw new Error(errorData.error || `Failed to regenerate post with feedback: ${res.statusText}`);
  }
  return res.json();
}

export async function approveAndSchedulePost(
  postId: string
): Promise<{ success: boolean; post: any }> {
  return updateKanbanPostStatus(postId, "scheduled");
}

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

export interface SocialMediaPostItem {
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

export interface InstagramKpis {
  totalReach: number;
  avgEngagementRate: number;
  totalSaves: number;
  totalLikes: number;
  totalComments: number;
  totalShares: number;
  totalEngagement: number;
  postCount: number;
}

export interface FacebookKpis {
  totalEngagement: number;
  avgEngagementRate: number;
  totalReactions: number;
  totalComments: number;
  totalShares: number;
  totalReach: number;
  avgEngagementPerPost: number;
  postCount: number;
}

export interface SocialMediaAnalyticsResponse {
  success: boolean;
  timestamp: string;
  data: {
    instagram: {
      kpis: InstagramKpis;
      topPost: SocialMediaPostItem | null;
      posts: SocialMediaPostItem[];
    };
    facebook: {
      kpis: FacebookKpis;
      topPost: SocialMediaPostItem | null;
      posts: SocialMediaPostItem[];
    };
  };
}

export async function fetchSocialMediaAnalytics(): Promise<SocialMediaAnalyticsResponse> {
  const res = await fetch("/api/marketing/social-media", {
    method: "GET",
    headers: { "Content-Type": "application/json" },
    cache: "no-store",
  });
  if (!res.ok) {
    throw new Error(`Failed to fetch social media analytics: ${res.statusText}`);
  }
  return res.json();
}

export async function triggerN8nSocialSync(): Promise<{
  success: boolean;
  triggered: boolean;
  message: string;
}> {
  const res = await fetch("/api/marketing/social-media/sync", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
  });
  if (!res.ok) {
    throw new Error(`Failed to trigger n8n social sync: ${res.statusText}`);
  }
  return res.json();
}
