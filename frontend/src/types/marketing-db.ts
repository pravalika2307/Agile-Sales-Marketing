/**
 * Type definitions for Marketing Database Entities, Enums, and Webhook Payloads
 * Generated and re-exported from Prisma Client
 */

import type {
  MonthlyTarget,
  Post,
  PostAnalytics,
  AiInsight,
  organizations,
} from "@prisma/client";

export { Platform, PostStatus, PostFormat } from "@prisma/client";

// Re-export primary entities
export type {
  MonthlyTarget,
  Post,
  PostAnalytics,
  AiInsight,
  organizations as Organization,
};

// Composite types for queries with relations
export type PostWithAnalytics = Post & {
  analytics: PostAnalytics | null;
};

export type PostWithRelations = Post & {
  analytics: PostAnalytics | null;
  organization: organizations;
};

export type MonthlyTargetWithClient = MonthlyTarget & {
  organization: organizations;
};

export type AiInsightWithClient = AiInsight & {
  organization: organizations;
};

// Frontend Kanban post item mapping
export interface KanbanPostItem {
  id: string;
  clientId: string;
  platform: "LINKEDIN" | "INSTAGRAM" | "FACEBOOK" | "X";
  externalPostId?: string | null;
  status: "BACKLOG" | "IN_PROGRESS" | "AWAITING_APPROVAL" | "SCHEDULED" | "POSTED";
  contentPillar: string;
  topic: string;
  format: "SINGLE_IMAGE" | "VIDEO" | "CAROUSEL";
  caption: string;
  permalink?: string | null;
  scheduledDate?: string | Date | null;
  aiCost?: number | null;
  regenerationRequested: boolean;
  imageChangeRequested: boolean;
  analytics?: {
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
  } | null;
}

// Webhook payload types for n8n integrations
export interface N8nPostAnalyticsWebhookPayload {
  postId: string;
  impressions?: number;
  reach?: number;
  likes?: number;
  comments?: number;
  shares?: number;
  saves?: number;
  totalEngagement?: number;
  engagementRate?: number;
  profileVisits?: number;
  linkClicks?: number;
}

export interface N8nAiInsightWebhookPayload {
  clientId: string;
  insightText: string;
  category: string;
}

export interface N8nPostStatusWebhookPayload {
  postId: string;
  status: "BACKLOG" | "IN_PROGRESS" | "AWAITING_APPROVAL" | "SCHEDULED" | "POSTED";
  externalPostId?: string;
  permalink?: string;
}
