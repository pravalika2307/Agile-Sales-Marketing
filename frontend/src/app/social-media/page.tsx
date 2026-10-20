"use client";

import * as React from "react";
import Link from "next/link";
import { AppShell } from "@/components/layout/app-shell";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ComposePostModal } from "@/components/social/compose-post-modal";
import { ManualLinkedInStatsModal } from "@/components/social/manual-linkedin-stats-modal";
import {
  Share2,
  Plus,
  BarChart3,
  TrendingUp,
  Users,
  Eye,
  Calendar,
  Search,
  Filter,
  CheckCircle2,
  ThumbsUp,
  MessageSquare,
  Sparkles,
  ExternalLink,
  Edit2,
  Trash2,
  AlertCircle,
} from "lucide-react";
import { LinkedInIcon, InstagramIcon, FacebookIcon } from "@/components/social/social-icons";

export interface SocialPostItem {
  id: string;
  title: string;
  preview: string;
  platforms: ("linkedin" | "instagram" | "facebook")[];
  status: "Published" | "Scheduled" | "Draft";
  publishedDate: string;
  impressions: number;
  reactions: number;
  comments: number;
  clicks: number;
  engagementRate: number;
}

const INITIAL_POSTS: SocialPostItem[] = [
  {
    id: "post-1",
    title: "Q4 B2B Working Capital Benchmark Report Release",
    preview: "Exclusive data from 140+ CFOs reveals that DSO can be reduced by 14 days with unified sales & receivables cadence...",
    platforms: ["linkedin", "facebook"],
    status: "Published",
    publishedDate: "Oct 18, 2026",
    impressions: 4820,
    reactions: 142,
    comments: 36,
    clicks: 98,
    engagementRate: 5.72,
  },
  {
    id: "post-2",
    title: "Case Study: Eliminating 14 Days of DSO in Healthcare",
    preview: "How regional healthcare providers automated invoice resolution without friction or manual SDR calling...",
    platforms: ["linkedin"],
    status: "Published",
    publishedDate: "Oct 14, 2026",
    impressions: 3240,
    reactions: 88,
    comments: 19,
    clicks: 64,
    engagementRate: 5.28,
  },
  {
    id: "post-3",
    title: "Behind the Scenes: Retell AI Telephony Workflow",
    preview: "A quick visual tour showing how our team coordinates voice agents with email outreach for 100% data truth...",
    platforms: ["instagram", "facebook"],
    status: "Scheduled",
    publishedDate: "Oct 24, 2026 (10:00 AM)",
    impressions: 0,
    reactions: 0,
    comments: 0,
    clicks: 0,
    engagementRate: 0,
  },
  {
    id: "post-4",
    title: "Monthly Revenue Operations Insights & Trends",
    preview: "Draft copy reviewing Q3 conversion rates and SDR touchpoint optimization strategies for executive review...",
    platforms: ["linkedin", "instagram"],
    status: "Draft",
    publishedDate: "Unscheduled",
    impressions: 0,
    reactions: 0,
    comments: 0,
    clicks: 0,
    engagementRate: 0,
  },
];

export default function SocialMediaPage() {
  const [posts, setPosts] = React.useState<SocialPostItem[]>(INITIAL_POSTS);
  const [searchQuery, setSearchQuery] = React.useState("");
  const [platformFilter, setPlatformFilter] = React.useState("ALL");
  const [statusFilter, setStatusFilter] = React.useState("ALL");

  // Modals state
  const [isComposeOpen, setIsComposeOpen] = React.useState(false);
  const [isLinkedInStatsOpen, setIsLinkedInStatsOpen] = React.useState(false);
  const [successBanner, setSuccessBanner] = React.useState<string | null>(null);

  const handlePostCreated = (newPost: any) => {
    const createdItem: SocialPostItem = {
      id: newPost.id,
      title: newPost.content.substring(0, 45) + (newPost.content.length > 45 ? "..." : ""),
      preview: newPost.content,
      platforms: newPost.platforms,
      status: newPost.status,
      publishedDate: newPost.scheduledFor,
      impressions: 0,
      reactions: 0,
      comments: 0,
      clicks: 0,
      engagementRate: 0,
    };
    setPosts([createdItem, ...posts]);
    setSuccessBanner("Social post successfully created and added to campaigns cadence.");
    setTimeout(() => setSuccessBanner(null), 4000);
  };

  const handleStatsSaved = (stats: any) => {
    setPosts((prev) =>
      prev.map((p) => {
        if (p.id === stats.postId || p.id === "post-1") {
          return {
            ...p,
            impressions: stats.impressions,
            reactions: stats.reactions,
            comments: stats.comments,
            clicks: stats.clicks,
            engagementRate: stats.engagementRate,
          };
        }
        return p;
      })
    );
    setSuccessBanner("LinkedIn stats manually recorded and KPIs updated.");
    setTimeout(() => setSuccessBanner(null), 4000);
  };

  // Filter posts
  const filteredPosts = posts.filter((post) => {
    if (searchQuery) {
      const q = searchQuery.toLowerCase();
      if (!post.title.toLowerCase().includes(q) && !post.preview.toLowerCase().includes(q)) {
        return false;
      }
    }
    if (platformFilter !== "ALL" && !post.platforms.includes(platformFilter as any)) {
      return false;
    }
    if (statusFilter !== "ALL" && post.status !== statusFilter) {
      return false;
    }
    return true;
  });

  return (
    <AppShell onNewCampaignClick={() => setIsComposeOpen(true)}>
      <div className="space-y-6">
        {/* Success Alert Banner */}
        {successBanner && (
          <div className="p-3.5 rounded-xl bg-emerald-50 border border-emerald-200 text-xs font-semibold text-emerald-800 flex items-center justify-between shadow-2xs animate-in fade-in">
            <div className="flex items-center gap-2">
              <CheckCircle2 className="w-4 h-4 text-emerald-600" />
              <span>{successBanner}</span>
            </div>
            <button
              onClick={() => setSuccessBanner(null)}
              className="text-emerald-500 hover:text-emerald-700 font-bold text-xs"
            >
              ✕
            </button>
          </div>
        )}

        {/* ── Top Header / Actions ────────────────────────────────────────── */}
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 pb-2 border-b border-slate-200/80">
          <div>
            <div className="flex items-center gap-2.5">
              <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-blue-600 via-indigo-600 to-purple-600 text-white flex items-center justify-center shadow-xs">
                <Share2 className="w-4 h-4" />
              </div>
              <h1 className="text-xl sm:text-2xl font-bold tracking-tight text-header">
                Social Media Marketing
              </h1>
              <span className="inline-flex items-center text-xs font-semibold text-purple-700 bg-purple-100 border border-purple-200 px-2.5 py-0.5 rounded-full">
                Multi-Platform Hub
              </span>
            </div>
            <p className="text-xs sm:text-sm text-slate-500 mt-1">
              Publish organic brand insights, schedule cross-channel drops, and log LinkedIn performance.
            </p>
          </div>

          <div className="flex items-center gap-2.5 flex-wrap">
            {/* Manual LinkedIn Stats Button */}
            <Button
              variant="outline"
              size="sm"
              onClick={() => setIsLinkedInStatsOpen(true)}
              className="text-xs font-medium border-blue-200 text-[#0A66C2] hover:bg-blue-50/70 shadow-2xs"
            >
              <LinkedInIcon className="w-3.5 h-3.5 mr-1.5" />
              <span>Enter LinkedIn Stats</span>
            </Button>

            {/* Compose Post Primary CTA */}
            <Button
              variant="primary"
              size="sm"
              onClick={() => setIsComposeOpen(true)}
              className="text-xs font-semibold bg-purple-600 hover:bg-purple-700 text-white shadow-xs"
            >
              <Plus className="w-3.5 h-3.5 mr-1" />
              <span>Compose Post</span>
            </Button>
          </div>
        </div>

        {/* ── Metric KPI Overview Cards ───────────────────────────────────── */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          <Card className="border border-slate-200/80 shadow-2xs bg-white">
            <CardContent className="p-4 sm:p-5">
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold uppercase tracking-wider text-slate-400">
                  Total Social Audience
                </span>
                <div className="w-8 h-8 rounded-lg bg-blue-50 text-blue-600 flex items-center justify-center">
                  <Users className="w-4 h-4" />
                </div>
              </div>
              <div className="mt-2 flex items-baseline gap-2">
                <span className="text-2xl sm:text-3xl font-extrabold tracking-tight text-header">
                  18,450
                </span>
                <span className="text-xs font-semibold text-emerald-600">+8.5%</span>
              </div>
              <p className="text-[11px] text-slate-400 mt-1">
                Followers across LinkedIn, IG, & Facebook
              </p>
            </CardContent>
          </Card>

          <Card className="border border-slate-200/80 shadow-2xs bg-white">
            <CardContent className="p-4 sm:p-5">
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold uppercase tracking-wider text-slate-400">
                  Total Impressions
                </span>
                <div className="w-8 h-8 rounded-lg bg-indigo-50 text-indigo-600 flex items-center justify-center">
                  <Eye className="w-4 h-4" />
                </div>
              </div>
              <div className="mt-2 flex items-baseline gap-2">
                <span className="text-2xl sm:text-3xl font-extrabold tracking-tight text-header">
                  42,900
                </span>
                <span className="text-xs font-semibold text-emerald-600">+19.4%</span>
              </div>
              <p className="text-[11px] text-slate-400 mt-1">
                Verified organic impressions this month
              </p>
            </CardContent>
          </Card>

          <Card className="border border-slate-200/80 shadow-2xs bg-white">
            <CardContent className="p-4 sm:p-5">
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold uppercase tracking-wider text-slate-400">
                  Avg. Engagement Rate
                </span>
                <div className="w-8 h-8 rounded-lg bg-purple-50 text-purple-600 flex items-center justify-center">
                  <TrendingUp className="w-4 h-4" />
                </div>
              </div>
              <div className="mt-2 flex items-baseline gap-2">
                <span className="text-2xl sm:text-3xl font-extrabold tracking-tight text-header">
                  4.85%
                </span>
                <span className="text-xs text-slate-400">(Industry avg: 2.1%)</span>
              </div>
              <p className="text-[11px] text-slate-400 mt-1">
                Reactions, comments, reposts & link clicks
              </p>
            </CardContent>
          </Card>

          <Card className="border border-slate-200/80 shadow-2xs bg-white">
            <CardContent className="p-4 sm:p-5">
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold uppercase tracking-wider text-slate-400">
                  Top Channel
                </span>
                <div className="w-8 h-8 rounded-lg bg-[#0A66C2]/10 text-[#0A66C2] flex items-center justify-center">
                  <LinkedInIcon className="w-4 h-4" />
                </div>
              </div>
              <div className="mt-2 flex items-baseline gap-2">
                <span className="text-xl sm:text-2xl font-bold tracking-tight text-header">
                  LinkedIn
                </span>
                <span className="inline-flex items-center text-[10px] font-semibold text-[#0A66C2] bg-blue-50 px-2 py-0.5 rounded-full">
                  68% Inbound Leads
                </span>
              </div>
              <p className="text-[11px] text-slate-400 mt-1">
                Highest commercial conversion driver
              </p>
            </CardContent>
          </Card>
        </div>

        {/* ── Social Campaigns & Posts Section ───────────────────────────── */}
        <Card className="border border-slate-200/80 shadow-2xs bg-white">
          {/* Filter Bar */}
          <div className="p-4 border-b border-slate-100 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
            <div className="flex items-center gap-2 flex-1 max-w-sm">
              <div className="relative w-full">
                <Input
                  icon={<Search className="w-3.5 h-3.5 text-slate-400" />}
                  placeholder="Filter social posts..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="h-8 text-xs bg-slate-50 border-slate-200"
                />
              </div>
            </div>

            <div className="flex items-center gap-2 flex-wrap">
              {/* Platform selector */}
              <select
                value={platformFilter}
                onChange={(e) => setPlatformFilter(e.target.value)}
                className="h-8 text-xs rounded-lg border border-slate-200 px-2.5 bg-white text-slate-700 font-medium"
              >
                <option value="ALL">All Channels</option>
                <option value="linkedin">LinkedIn</option>
                <option value="instagram">Instagram</option>
                <option value="facebook">Facebook</option>
              </select>

              {/* Status selector */}
              <select
                value={statusFilter}
                onChange={(e) => setStatusFilter(e.target.value)}
                className="h-8 text-xs rounded-lg border border-slate-200 px-2.5 bg-white text-slate-700 font-medium"
              >
                <option value="ALL">All Statuses</option>
                <option value="Published">Published</option>
                <option value="Scheduled">Scheduled</option>
                <option value="Draft">Draft</option>
              </select>
            </div>
          </div>

          {/* Posts Table */}
          <CardContent className="p-0">
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead className="bg-slate-50/70 text-slate-400 font-semibold border-b border-slate-100 uppercase tracking-wider text-[10px]">
                  <tr>
                    <th className="py-3 px-4">Post & Campaign</th>
                    <th className="py-3 px-4">Channels</th>
                    <th className="py-3 px-4">Schedule / Date</th>
                    <th className="py-3 px-4">Status</th>
                    <th className="py-3 px-4">Impressions</th>
                    <th className="py-3 px-4">Interactions</th>
                    <th className="py-3 px-4">Engagement</th>
                    <th className="py-3 px-4 text-right">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100 text-slate-600">
                  {filteredPosts.length === 0 ? (
                    <tr>
                      <td colSpan={8} className="py-8 text-center text-slate-400">
                        No social posts found matching the filter criteria.
                      </td>
                    </tr>
                  ) : (
                    filteredPosts.map((post) => (
                      <tr key={post.id} className="hover:bg-slate-50/50 transition-colors">
                        <td className="py-3.5 px-4 max-w-xs">
                          <div className="font-semibold text-header truncate">{post.title}</div>
                          <div className="text-[11px] text-slate-400 line-clamp-1 mt-0.5">
                            {post.preview}
                          </div>
                        </td>

                        <td className="py-3.5 px-4">
                          <div className="flex items-center gap-1.5">
                            {post.platforms.includes("linkedin") && (
                              <span
                                title="LinkedIn"
                                className="w-6 h-6 rounded-md bg-blue-50 text-[#0A66C2] border border-blue-200 flex items-center justify-center"
                              >
                                <LinkedInIcon className="w-3.5 h-3.5" />
                              </span>
                            )}
                            {post.platforms.includes("instagram") && (
                              <span
                                title="Instagram"
                                className="w-6 h-6 rounded-md bg-pink-50 text-pink-600 border border-pink-200 flex items-center justify-center"
                              >
                                <InstagramIcon className="w-3.5 h-3.5" />
                              </span>
                            )}
                            {post.platforms.includes("facebook") && (
                              <span
                                title="Facebook"
                                className="w-6 h-6 rounded-md bg-indigo-50 text-[#1877F2] border border-indigo-200 flex items-center justify-center"
                              >
                                <FacebookIcon className="w-3.5 h-3.5" />
                              </span>
                            )}
                          </div>
                        </td>

                        <td className="py-3.5 px-4 text-[11px] text-slate-600 font-medium">
                          {post.publishedDate}
                        </td>

                        <td className="py-3.5 px-4">
                          {post.status === "Published" && (
                            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200/60">
                              <span className="w-1.5 h-1.5 rounded-full bg-emerald-500" />
                              Published
                            </span>
                          )}
                          {post.status === "Scheduled" && (
                            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold bg-purple-50 text-purple-700 border border-purple-200/60">
                              <Calendar className="w-3 h-3 text-purple-600" />
                              Scheduled
                            </span>
                          )}
                          {post.status === "Draft" && (
                            <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-semibold bg-slate-100 text-slate-600">
                              Draft
                            </span>
                          )}
                        </td>

                        <td className="py-3.5 px-4 font-mono font-medium text-slate-700">
                          {post.impressions > 0 ? post.impressions.toLocaleString() : "—"}
                        </td>

                        <td className="py-3.5 px-4 text-[11px]">
                          {post.reactions > 0 || post.comments > 0 ? (
                            <div className="flex items-center gap-2">
                              <span className="flex items-center gap-1 text-slate-700">
                                <ThumbsUp className="w-3 h-3 text-blue-500" />
                                {post.reactions}
                              </span>
                              <span className="flex items-center gap-1 text-slate-700">
                                <MessageSquare className="w-3 h-3 text-emerald-500" />
                                {post.comments}
                              </span>
                            </div>
                          ) : (
                            <span className="text-slate-400">—</span>
                          )}
                        </td>

                        <td className="py-3.5 px-4">
                          {post.engagementRate > 0 ? (
                            <span className="inline-flex items-center font-bold text-xs text-blue-700 bg-blue-50 border border-blue-200 px-2 py-0.5 rounded-md">
                              {post.engagementRate}%
                            </span>
                          ) : (
                            <span className="text-slate-400">—</span>
                          )}
                        </td>

                        <td className="py-3.5 px-4 text-right">
                          <div className="flex items-center justify-end gap-1.5">
                            <button
                              type="button"
                              onClick={() => setIsLinkedInStatsOpen(true)}
                              className="px-2 py-1 rounded-md text-[11px] font-semibold text-blue-600 hover:text-blue-800 hover:bg-blue-50 transition-colors border border-blue-200/60"
                              title="Enter/Update LinkedIn Metrics"
                            >
                              Update Stats
                            </button>
                          </div>
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Compose Post Modal */}
      <ComposePostModal
        isOpen={isComposeOpen}
        onClose={() => setIsComposeOpen(false)}
        onPostCreated={handlePostCreated}
      />

      {/* Manual LinkedIn Stats Modal */}
      <ManualLinkedInStatsModal
        isOpen={isLinkedInStatsOpen}
        onClose={() => setIsLinkedInStatsOpen(false)}
        onStatsSaved={handleStatsSaved}
      />
    </AppShell>
  );
}
